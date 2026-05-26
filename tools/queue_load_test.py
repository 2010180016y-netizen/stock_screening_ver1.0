from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcb_alt.auth import hash_password
from vcb_alt.config import AppConfig
from vcb_alt.db import connect, init_db
from vcb_alt.job_queue import enqueue_scan_job, queue_status, run_queued_scan_jobs
from vcb_alt.sample_data import SAMPLE_TICKERS
from vcb_alt.tenant_store import add_user_watchlist, init_saas_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local queue-backed SaaS load simulation.")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--tickers", type=int, default=30)
    parser.add_argument("--worker-limit", type=int, default=100)
    args = parser.parse_args()
    report = run_queue_load_simulation(args.users, args.tickers, args.worker_limit)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0 if report["errors"] == 0 and report["completed_jobs"] == args.users else 1


def run_queue_load_simulation(users: int = 1000, tickers: int = 30, worker_limit: int = 100) -> dict[str, int | float | str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = AppConfig(
            database_url="sqlite:///./data/queue-load-test.db",
            log_level="INFO",
            timezone="Asia/Seoul",
            data_provider="sample",
            external_api_enabled=False,
            root_dir=root,
            data_dir=root / "data",
            log_dir=root / "logs",
            user_auth_enabled=True,
            user_registration_enabled=False,
            scan_queue_enabled=True,
        )
        started = perf_counter()
        errors = 0
        with connect(config) as conn:
            init_db(conn)
            init_saas_db(conn)
            password_hash = hash_password("queue-load-password")
            ticker_universe = _ticker_universe(tickers)
            for index in range(users):
                user = _insert_user(conn, index, password_hash)
                try:
                    add_user_watchlist(conn, user, ticker_universe)
                    enqueue_scan_job(conn, user)
                except Exception:
                    errors += 1
            while True:
                status = queue_status(conn)
                if status["queued"] == 0 and status["running"] == 0:
                    break
                run_queued_scan_jobs(config, conn, limit=worker_limit)
            final_status = queue_status(conn)
            eval_rows = conn.execute("SELECT COUNT(*) AS count FROM tenant_evaluations").fetchone()
        elapsed = perf_counter() - started
        evaluations = int(eval_rows["count"])
        return {
            "users": users,
            "tickers_per_user": tickers,
            "queued_jobs": users,
            "completed_jobs": int(final_status["completed"]),
            "failed_jobs": int(final_status["failed"]),
            "tenant_evaluations": evaluations,
            "elapsed_seconds": round(elapsed, 3),
            "evals_per_second": round(evaluations / elapsed, 2) if elapsed else evaluations,
            "errors": errors,
            "tenant_isolation": "schema-scoped",
        }


def _insert_user(conn: object, index: int, password_hash: str) -> dict[str, str]:
    tenant_id = f"tenant_queue_{index}"
    user_id = f"user_queue_{index}"
    now = "2026-05-22T00:00:00+00:00"
    conn.execute("INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)", (tenant_id, tenant_id, now))
    conn.execute(
        """
        INSERT INTO users (id, tenant_id, email, password_hash, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, tenant_id, f"queue{index}@example.com", password_hash, "owner", now),
    )
    conn.commit()
    return {"id": user_id, "tenant_id": tenant_id, "email": f"queue{index}@example.com", "role": "owner"}


def _ticker_universe(size: int) -> list[str]:
    base = list(SAMPLE_TICKERS)
    while len(base) < size:
        base.append(f"T{len(base):04d}")
    return base[:size]


if __name__ == "__main__":
    raise SystemExit(main())

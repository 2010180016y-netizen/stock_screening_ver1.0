from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path
from statistics import quantiles
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vcb_alt.auth import hash_password
from vcb_alt.config import AppConfig
from vcb_alt.db import connect, init_db
from vcb_alt.sample_data import SAMPLE_TICKERS, get_snapshot
from vcb_alt.scoring import evaluate_snapshot
from vcb_alt.tenant_store import add_user_watchlist, init_saas_db, list_user_watchlist


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local 1000-user SaaS readiness load simulation.")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--tickers", type=int, default=30)
    args = parser.parse_args()
    report = run_load_simulation(args.users, args.tickers)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0 if report["errors"] == 0 else 1


def run_load_simulation(users: int = 1000, tickers: int = 30) -> dict[str, float | int | str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = AppConfig(
            database_url="sqlite:///./data/load-test.db",
            log_level="INFO",
            timezone="Asia/Seoul",
            data_provider="sample",
            external_api_enabled=False,
            root_dir=root,
            data_dir=root / "data",
            log_dir=root / "logs",
            user_auth_enabled=True,
            user_registration_enabled=False,
        )
        with connect(config) as conn:
            init_db(conn)
            init_saas_db(conn)
            password_hash = hash_password("load-test-password")
            ticker_universe = _ticker_universe(tickers)
            latencies_ms: list[float] = []
            errors = 0
            start = perf_counter()
            for index in range(users):
                user = _insert_user(conn, index, password_hash)
                user_start = perf_counter()
                try:
                    add_user_watchlist(conn, user, ticker_universe)
                    for ticker in ticker_universe:
                        evaluate_snapshot(get_snapshot(ticker))
                except Exception:
                    errors += 1
                latencies_ms.append((perf_counter() - user_start) * 1000)
            elapsed = perf_counter() - start
            isolation_ok = _tenant_isolation_ok(conn)
        p95 = quantiles(latencies_ms, n=20)[18] if len(latencies_ms) >= 20 else max(latencies_ms or [0])
        evaluations = users * tickers
        return {
            "users": users,
            "tickers_per_user": tickers,
            "evaluations": evaluations,
            "elapsed_seconds": round(elapsed, 3),
            "evals_per_second": round(evaluations / elapsed, 2) if elapsed else evaluations,
            "p95_user_flow_ms": round(p95, 3),
            "errors": errors,
            "tenant_isolation": "passed" if isolation_ok else "failed",
        }


def _insert_user(conn: sqlite3.Connection, index: int, password_hash: str) -> dict[str, str]:
    tenant_id = f"tenant_load_{index}"
    user_id = f"user_load_{index}"
    now = "2026-05-19T00:00:00+00:00"
    conn.execute("INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)", (tenant_id, tenant_id, now))
    conn.execute(
        """
        INSERT INTO users (id, tenant_id, email, password_hash, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, tenant_id, f"user{index}@example.com", password_hash, "owner", now),
    )
    conn.commit()
    return {"id": user_id, "tenant_id": tenant_id, "email": f"user{index}@example.com", "role": "owner"}


def _ticker_universe(size: int) -> list[str]:
    base = list(SAMPLE_TICKERS)
    while len(base) < size:
        base.append(f"T{len(base):04d}")
    return base[:size]


def _tenant_isolation_ok(conn: sqlite3.Connection) -> bool:
    first = {"id": "user_load_0", "tenant_id": "tenant_load_0"}
    second = {"id": "user_load_1", "tenant_id": "tenant_load_1"}
    first_rows = list_user_watchlist(conn, first)
    second_rows = list_user_watchlist(conn, second)
    return bool(first_rows) and bool(second_rows) and first_rows == second_rows


if __name__ == "__main__":
    raise SystemExit(main())

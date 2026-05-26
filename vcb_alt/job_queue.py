from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .db import record_failure
from .errors import NotFoundError, ValidationError
from .logging_utils import utc_now
from .market_universe import scan_market_universe
from .providers import get_snapshot
from .scoring import evaluate_snapshot
from .tenant_store import list_user_watchlist, save_user_evaluation


def enqueue_scan_job(conn: Any, user: dict[str, Any]) -> dict[str, Any]:
    job_id = f"job_{uuid.uuid4().hex}"
    now = utc_now()
    conn.execute(
        """
        INSERT INTO scan_jobs (
            id, tenant_id, user_id, status, requested_by, request_json,
            result_json, error_code, message, attempts, created_at, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            user["tenant_id"],
            user["id"],
            "queued",
            user["email"],
            json.dumps({"kind": "tenant_watchlist_scan"}, ensure_ascii=False, sort_keys=True),
            None,
            None,
            "Queued for background scan.",
            0,
            now,
            None,
            None,
        ),
    )
    conn.commit()
    return {"id": job_id, "status": "queued", "created_at": now}


def list_scan_jobs(conn: Any, user: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, status, requested_by, request_json, result_json, error_code, message,
               attempts, created_at, started_at, finished_at
        FROM scan_jobs
        WHERE tenant_id = ? AND user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user["tenant_id"], user["id"], limit),
    ).fetchall()
    return [_decode_job(row) for row in rows]


def get_scan_job(conn: Any, user: dict[str, Any], job_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, status, requested_by, request_json, result_json, error_code, message,
               attempts, created_at, started_at, finished_at
        FROM scan_jobs
        WHERE id = ? AND tenant_id = ? AND user_id = ?
        """,
        (job_id, user["tenant_id"], user["id"]),
    ).fetchone()
    if row is None:
        raise NotFoundError("Scan job not found.")
    return _decode_job(row)


def run_queued_scan_jobs(config: Any, conn: Any, *, limit: int = 5) -> dict[str, Any]:
    recovered = recover_stale_jobs(conn)
    processed = 0
    failed = 0
    for _ in range(max(0, limit)):
        job = _claim_next_job(conn)
        if job is None:
            break
        processed += 1
        try:
            result = _run_tenant_scan(config, conn, job)
            _complete_job(conn, job["id"], result)
        except Exception as exc:  # pragma: no cover - final safety net
            failed += 1
            message = str(exc) or exc.__class__.__name__
            conn.rollback()
            _fail_job(conn, job["id"], "SCAN_JOB_FAILED", message)
            record_failure(conn, "scan-worker", "SCAN_JOB_FAILED", message, {"job_id": job["id"]})
    return {"processed": processed, "failed": failed, "recovered": recovered}


def queue_status(conn: Any, tenant_id: str | None = None) -> dict[str, Any]:
    where = "WHERE tenant_id = ?" if tenant_id else ""
    params = (tenant_id,) if tenant_id else ()
    rows = conn.execute(
        f"""
        SELECT status, COUNT(*) AS count
        FROM scan_jobs
        {where}
        GROUP BY status
        """,
        params,
    ).fetchall()
    oldest = conn.execute(
        f"""
        SELECT created_at
        FROM scan_jobs
        {where + " AND" if tenant_id else "WHERE"} status = ?
        ORDER BY created_at
        LIMIT 1
        """,
        (*params, "queued"),
    ).fetchone()
    status_counts = {str(row["status"]): int(row["count"]) for row in rows}
    return {
        "status_counts": status_counts,
        "queued": status_counts.get("queued", 0),
        "running": status_counts.get("running", 0),
        "failed": status_counts.get("failed", 0),
        "completed": status_counts.get("completed", 0),
        "oldest_queued_at": _iso_value(oldest["created_at"]) if oldest else None,
    }


def recover_stale_jobs(conn: Any, *, max_running_seconds: int = 900, max_attempts: int = 3) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_running_seconds)).isoformat()
    retry = conn.execute(
        """
        UPDATE scan_jobs
        SET status = ?, message = ?
        WHERE status = ? AND started_at IS NOT NULL AND started_at < ? AND attempts < ?
        """,
        ("queued", "Recovered stale running job.", "running", cutoff, max_attempts),
    )
    fail = conn.execute(
        """
        UPDATE scan_jobs
        SET status = ?, error_code = ?, message = ?, finished_at = ?
        WHERE status = ? AND started_at IS NOT NULL AND started_at < ? AND attempts >= ?
        """,
        ("failed", "SCAN_JOB_STALE", "Stale running job exceeded max attempts.", utc_now(), "running", cutoff, max_attempts),
    )
    conn.commit()
    return {
        "requeued": retry.rowcount if retry.rowcount is not None else 0,
        "failed": fail.rowcount if fail.rowcount is not None else 0,
    }


def _claim_next_job(conn: Any) -> dict[str, Any] | None:
    if getattr(conn, "dialect", "") == "postgresql":
        # Postgres workers can overlap in serverless/Cron environments; SKIP LOCKED
        # lets each worker claim a different job without blocking the whole queue.
        row = conn.execute(
            """
            WITH next_job AS (
                SELECT id
                FROM scan_jobs
                WHERE status = ?
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE scan_jobs AS s
            SET status = ?, attempts = s.attempts + 1, started_at = ?, message = ?
            FROM next_job
            WHERE s.id = next_job.id
            RETURNING s.id, s.tenant_id, s.user_id, s.attempts
            """,
            ("queued", "running", utc_now(), "Worker started."),
        ).fetchone()
        conn.commit()
        return dict(row) if row is not None else None

    row = conn.execute(
        """
        SELECT id, tenant_id, user_id, attempts
        FROM scan_jobs
        WHERE status = ?
        ORDER BY created_at
        LIMIT 1
        """,
        ("queued",),
    ).fetchone()
    if row is None:
        return None
    job = dict(row)
    cursor = conn.execute(
        """
        UPDATE scan_jobs
        SET status = ?, attempts = ?, started_at = ?, message = ?
        WHERE id = ? AND status = ?
        """,
        ("running", int(job["attempts"]) + 1, utc_now(), "Worker started.", job["id"], "queued"),
    )
    conn.commit()
    if cursor.rowcount != 1:
        return None
    return job


def _run_tenant_scan(config: Any, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
    user = {"tenant_id": job["tenant_id"], "id": job["user_id"]}
    if getattr(config, "scan_mode", "watchlist") == "market_universe":
        report = scan_market_universe(config)
        for item in report.evaluations:
            save_user_evaluation(conn, user, item, commit=False)
        conn.commit()
        return report.to_api_dict()

    items = list_user_watchlist(conn, user)
    evaluations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in items:
        ticker = item["ticker"]
        try:
            result = evaluate_snapshot(get_snapshot(config, ticker))
            save_user_evaluation(conn, user, result, commit=False)
            evaluations.append(result.to_dict())
        except Exception as exc:
            failures.append({"ticker": ticker, "code": exc.__class__.__name__, "message": str(exc)})
    return {"items": evaluations, "failures": failures, "count": len(evaluations)}


def _complete_job(conn: Any, job_id: str, result: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE scan_jobs
        SET status = ?, result_json = ?, error_code = ?, message = ?, finished_at = ?
        WHERE id = ?
        """,
        ("completed", json.dumps(result, ensure_ascii=False, sort_keys=True), None, "Scan completed.", utc_now(), job_id),
    )
    conn.commit()


def _fail_job(conn: Any, job_id: str, code: str, message: str) -> None:
    conn.execute(
        """
        UPDATE scan_jobs
        SET status = ?, error_code = ?, message = ?, finished_at = ?
        WHERE id = ?
        """,
        ("failed", code, message, utc_now(), job_id),
    )
    conn.commit()


def _decode_job(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in ("request_json", "result_json"):
        raw_value = data.get(key)
        if raw_value:
            data[key.removesuffix("_json")] = raw_value if isinstance(raw_value, (dict, list)) else json.loads(raw_value)
        else:
            data.pop(key, None)
            data[key.removesuffix("_json")] = None
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
    return data


def _iso_value(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def validate_job_limit(value: int) -> int:
    if value < 1 or value > 100:
        raise ValidationError("Job worker limit must be between 1 and 100.")
    return value

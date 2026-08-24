from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .db import record_failure, record_provider_alert
from .errors import NotFoundError, ValidationError
from .logging_utils import utc_now
from .market_universe import ensure_live_market_scan_report, scan_market_universe
from .models import EvaluationResult
from .provider_resilience import provider_alert_payload
from .providers import get_snapshot
from .scoring import evaluate_snapshot
from .tenant_store import list_user_watchlist, save_user_evaluation

MARKET_SCAN_KEY = "market_universe:default"
MARKET_SCAN_MAX_ATTEMPTS = 3


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
    market_recovered = recover_stale_market_scan_jobs(conn)
    processed = 0
    failed = 0
    for _ in range(max(0, limit)):
        market_job = _claim_next_market_scan_job(conn)
        if market_job is not None:
            processed += 1
            try:
                result = _run_market_scan_snapshot(config, conn, market_job)
                _complete_market_scan_job(conn, market_job["id"], result)
            except Exception as exc:  # pragma: no cover - final safety net
                failed += 1
                message = str(exc) or exc.__class__.__name__
                conn.rollback()
                _fail_market_scan_job(conn, market_job["id"], "MARKET_SCAN_FAILED", message, int(market_job["attempts"]))
                record_failure(conn, "market-scan-worker", "MARKET_SCAN_FAILED", message, {"job_id": market_job["id"]})
                _record_provider_alert_if_needed(conn, exc, "market_scan_worker", {"job_id": market_job["id"]})
            continue
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
            _record_provider_alert_if_needed(conn, exc, "scan_worker", {"job_id": job["id"]})
    return {"processed": processed, "failed": failed, "recovered": recovered, "market_recovered": market_recovered}


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
    market_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM market_scan_snapshots
        GROUP BY status
        """
    ).fetchall()
    latest_market = conn.execute(
        """
        SELECT id, status, message, completed_at, expires_at, next_attempt_at
        FROM market_scan_snapshots
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    market_counts = {str(row["status"]): int(row["count"]) for row in market_rows}
    return {
        "status_counts": status_counts,
        "queued": status_counts.get("queued", 0),
        "running": status_counts.get("running", 0),
        "failed": status_counts.get("failed", 0),
        "completed": status_counts.get("completed", 0),
        "oldest_queued_at": _iso_value(oldest["created_at"]) if oldest else None,
        "market_scan_snapshots": {
            "status_counts": market_counts,
            "queued": market_counts.get("queued", 0),
            "running": market_counts.get("running", 0),
            "completed": market_counts.get("completed", 0),
            "failed": market_counts.get("failed", 0),
            "dead_letter": market_counts.get("dead_letter", 0),
            "latest": _decode_market_scan_row(latest_market) if latest_market else None,
        },
    }


def _record_provider_alert_if_needed(
    conn: Any,
    exc: BaseException,
    context: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    alert = provider_alert_payload(exc, context=context, metadata=metadata)
    if alert is None:
        return
    record_provider_alert(
        conn,
        alert["provider"],
        alert["event_type"],
        alert["severity"],
        alert["code"],
        alert["message"],
        recovery=alert.get("recovery", ""),
        metadata=alert.get("metadata", {}),
        tenant_id=(metadata or {}).get("tenant_id"),
    )


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


def enqueue_or_get_market_scan_snapshot(config: Any, conn: Any, user: dict[str, Any]) -> dict[str, Any]:
    fresh = get_fresh_market_scan_snapshot(config, conn)
    if fresh is not None:
        persist_market_snapshot_for_user(conn, user, fresh["report"])
        return {"state": "fresh", "status": "completed", "report": fresh["report"], "snapshot": fresh["snapshot"]}

    recover_stale_market_scan_jobs(conn)
    active = get_active_market_scan_job(conn)
    if active is not None:
        return {"state": "pending", "status": active["status"], "job": active}

    try:
        job = _enqueue_market_scan_snapshot_for_worker(
            conn,
            requested_by=str(user.get("email") or user.get("id") or "authenticated-user"),
        )
    except Exception:
        conn.rollback()
        active = get_active_market_scan_job(conn)
        if active is not None:
            return {"state": "pending", "status": active["status"], "job": active}
        raise
    return {
        "state": "queued",
        "status": "queued",
        "job": job,
    }


def _enqueue_market_scan_snapshot_for_worker(conn: Any, *, requested_by: str) -> dict[str, Any]:
    now = utc_now()
    job_id = f"market_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO market_scan_snapshots (
            id, scan_key, status, requested_by, report_json, selected_json,
            provider_metadata_json, failures_json, error_code, message,
            attempts, created_at, started_at, completed_at, expires_at, next_attempt_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            MARKET_SCAN_KEY,
            "queued",
            requested_by,
            None,
            None,
            None,
            None,
            None,
            "Queued market-universe snapshot refresh.",
            0,
            now,
            None,
            None,
            None,
            now,
        ),
    )
    conn.commit()
    return {
        "id": job_id,
        "status": "queued",
        "scan_key": MARKET_SCAN_KEY,
        "created_at": now,
        "message": "Queued market-universe snapshot refresh.",
    }


# The market-scan snapshot is one shared resource, so any authenticated user can see the
# job for it. requested_by holds the email of whoever triggered the scan, which means
# returning the raw row hands one tenant a user identity from another. Strip the
# operator-only fields at the API boundary; the column stays for operations and logs.
INTERNAL_MARKET_SCAN_FIELDS = ("requested_by",)


def public_market_scan_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {key: value for key, value in job.items() if key not in INTERNAL_MARKET_SCAN_FIELDS}


def public_market_scan_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    if "job" not in outcome:
        return outcome
    return {**outcome, "job": public_market_scan_job(outcome["job"])}


def get_market_scan_job(conn: Any, job_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, scan_key, status, requested_by, report_json, selected_json, provider_metadata_json,
               failures_json, error_code, message, attempts, created_at, started_at, completed_at,
               expires_at, next_attempt_at
        FROM market_scan_snapshots
        WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError("Market scan job not found.")
    return _decode_market_scan_row(row)


def get_active_market_scan_job(conn: Any) -> dict[str, Any] | None:
    now = utc_now()
    row = conn.execute(
        """
        SELECT id, scan_key, status, requested_by, error_code, message, attempts,
               created_at, started_at, completed_at, expires_at, next_attempt_at
        FROM market_scan_snapshots
        WHERE scan_key = ? AND status IN (?, ?)
        ORDER BY created_at
        LIMIT 1
        """,
        (MARKET_SCAN_KEY, "queued", "running"),
    ).fetchone()
    if row is None:
        return None
    data = _decode_market_scan_row(row)
    next_attempt_at = data.get("next_attempt_at")
    data["ready_to_run"] = not next_attempt_at or str(next_attempt_at) <= now
    return data


def get_fresh_market_scan_snapshot(config: Any, conn: Any) -> dict[str, Any] | None:
    now = utc_now()
    row = conn.execute(
        """
        SELECT id, scan_key, status, report_json, selected_json, provider_metadata_json,
               failures_json, message, attempts, created_at, started_at, completed_at,
               expires_at, next_attempt_at
        FROM market_scan_snapshots
        WHERE scan_key = ? AND status = ? AND expires_at IS NOT NULL AND expires_at > ?
        ORDER BY completed_at DESC
        LIMIT 1
        """,
        (MARKET_SCAN_KEY, "completed", now),
    ).fetchone()
    if row is None:
        return None
    data = _decode_market_scan_row(row)
    report = data.get("report")
    if not isinstance(report, dict):
        return None
    completed_at = data.get("completed_at")
    report = dict(report)
    try:
        ensure_live_market_scan_report(config, report, source="fresh durable market scan snapshot")
    except ValidationError:
        return None
    report["snapshot"] = {
        "id": data["id"],
        "status": "fresh",
        "scan_key": data["scan_key"],
        "completed_at": completed_at,
        "expires_at": data.get("expires_at"),
        "freshness_seconds": _age_seconds(completed_at),
        "served_from": "durable_snapshot",
    }
    return {"report": report, "snapshot": report["snapshot"]}


def persist_market_snapshot_for_user(conn: Any, user: dict[str, Any], report: dict[str, Any]) -> None:
    items = report.get("items") if isinstance(report, dict) else None
    if not isinstance(items, list):
        return
    for item in items:
        if isinstance(item, dict):
            save_user_evaluation(conn, user, EvaluationResult(**item), commit=False)
    conn.commit()


def recover_stale_market_scan_jobs(
    conn: Any,
    *,
    max_running_seconds: int = 900,
    max_attempts: int = MARKET_SCAN_MAX_ATTEMPTS,
) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_running_seconds)).isoformat()
    retry = conn.execute(
        """
        UPDATE market_scan_snapshots
        SET status = ?, message = ?, started_at = ?, next_attempt_at = ?
        WHERE status = ? AND started_at IS NOT NULL AND started_at < ? AND attempts < ?
        """,
        ("queued", "Recovered stale running market scan.", None, utc_now(), "running", cutoff, max_attempts),
    )
    dead = conn.execute(
        """
        UPDATE market_scan_snapshots
        SET status = ?, error_code = ?, message = ?, completed_at = ?, next_attempt_at = ?
        WHERE status = ? AND started_at IS NOT NULL AND started_at < ? AND attempts >= ?
        """,
        (
            "dead_letter",
            "MARKET_SCAN_STALE",
            "Stale running market scan exceeded max attempts.",
            utc_now(),
            None,
            "running",
            cutoff,
            max_attempts,
        ),
    )
    conn.commit()
    return {
        "requeued": retry.rowcount if retry.rowcount is not None else 0,
        "dead_lettered": dead.rowcount if dead.rowcount is not None else 0,
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


def _claim_next_market_scan_job(conn: Any) -> dict[str, Any] | None:
    now = utc_now()
    if getattr(conn, "dialect", "") == "postgresql":
        row = conn.execute(
            """
            WITH next_job AS (
                SELECT id
                FROM market_scan_snapshots
                WHERE status = ? AND scan_key = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE market_scan_snapshots AS s
            SET status = ?, attempts = s.attempts + 1, started_at = ?, message = ?
            FROM next_job
            WHERE s.id = next_job.id
            RETURNING s.id, s.scan_key, s.attempts
            """,
            ("queued", MARKET_SCAN_KEY, now, "running", now, "Worker started market-universe snapshot refresh."),
        ).fetchone()
        conn.commit()
        return dict(row) if row is not None else None

    row = conn.execute(
        """
        SELECT id, scan_key, attempts
        FROM market_scan_snapshots
        WHERE status = ? AND scan_key = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        ORDER BY created_at
        LIMIT 1
        """,
        ("queued", MARKET_SCAN_KEY, now),
    ).fetchone()
    if row is None:
        return None
    job = dict(row)
    cursor = conn.execute(
        """
        UPDATE market_scan_snapshots
        SET status = ?, attempts = ?, started_at = ?, message = ?
        WHERE id = ? AND status = ?
        """,
        (
            "running",
            int(job["attempts"]) + 1,
            now,
            "Worker started market-universe snapshot refresh.",
            job["id"],
            "queued",
        ),
    )
    conn.commit()
    if cursor.rowcount != 1:
        return None
    job["attempts"] = int(job["attempts"]) + 1
    return job


def _run_tenant_scan(config: Any, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
    user = {"tenant_id": job["tenant_id"], "id": job["user_id"]}
    if getattr(config, "scan_mode", "watchlist") == "market_universe":
        fresh = get_fresh_market_scan_snapshot(config, conn)
        if fresh is not None:
            persist_market_snapshot_for_user(conn, user, fresh["report"])
            return fresh["report"]
        active = get_active_market_scan_job(conn)
        if active is None:
            active = _enqueue_market_scan_snapshot_for_worker(
                conn,
                requested_by=f"tenant_job:{job['tenant_id']}:{job['user_id']}",
            )
        return {
            "state": "pending",
            "status": active["status"],
            "job": active,
            "message": "Tenant job is waiting for a worker-owned market-universe snapshot.",
        }

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


def _run_market_scan_snapshot(config: Any, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
    report = scan_market_universe(config).to_api_dict()
    report["snapshot"] = {
        "id": job["id"],
        "scan_key": job.get("scan_key") or MARKET_SCAN_KEY,
        "status": "completed",
        "served_from": "worker_refresh",
    }
    report["snapshot_ttl_seconds"] = int(float(getattr(config, "intraday_cache_ttl_seconds", 60)))
    return report


def _complete_market_scan_job(
    conn: Any,
    job_id: str,
    result: dict[str, Any],
    *,
    insert_if_missing: bool = False,
) -> None:
    now = utc_now()
    ttl_seconds = max(1, int(float(result.get("snapshot_ttl_seconds") or 0) or 0))
    if ttl_seconds <= 1:
        ttl_seconds = 60
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    selected = result.get("selection", {}).get("selected", []) if isinstance(result.get("selection"), dict) else []
    provider_metadata = {
        "scan_mode": result.get("scan_mode"),
        "universe": result.get("universe"),
        "prefilter": result.get("prefilter"),
        "count": result.get("count"),
        "elapsed_ms": result.get("elapsed_ms"),
    }
    params = (
        "completed",
        json.dumps(result, ensure_ascii=False, sort_keys=True),
        json.dumps(selected, ensure_ascii=False, sort_keys=True),
        json.dumps(provider_metadata, ensure_ascii=False, sort_keys=True),
        json.dumps(result.get("failures", []), ensure_ascii=False, sort_keys=True),
        None,
        "Market-universe snapshot completed.",
        now,
        expires_at,
        None,
        job_id,
    )
    cursor = conn.execute(
        """
        UPDATE market_scan_snapshots
        SET status = ?, report_json = ?, selected_json = ?, provider_metadata_json = ?,
            failures_json = ?, error_code = ?, message = ?, completed_at = ?, expires_at = ?,
            next_attempt_at = ?
        WHERE id = ?
        """,
        params,
    )
    if insert_if_missing and (cursor.rowcount is None or cursor.rowcount == 0):
        conn.execute(
            """
            INSERT INTO market_scan_snapshots (
                id, scan_key, status, requested_by, report_json, selected_json,
                provider_metadata_json, failures_json, error_code, message, attempts,
                created_at, started_at, completed_at, expires_at, next_attempt_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                MARKET_SCAN_KEY,
                "completed",
                "worker-inline",
                json.dumps(result, ensure_ascii=False, sort_keys=True),
                json.dumps(selected, ensure_ascii=False, sort_keys=True),
                json.dumps(provider_metadata, ensure_ascii=False, sort_keys=True),
                json.dumps(result.get("failures", []), ensure_ascii=False, sort_keys=True),
                None,
                "Market-universe snapshot completed.",
                1,
                now,
                now,
                now,
                expires_at,
                None,
            ),
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


def _fail_market_scan_job(conn: Any, job_id: str, code: str, message: str, attempts: int) -> None:
    now_dt = datetime.now(timezone.utc)
    if attempts < MARKET_SCAN_MAX_ATTEMPTS:
        backoff_seconds = min(300, 30 * attempts)
        conn.execute(
            """
            UPDATE market_scan_snapshots
            SET status = ?, error_code = ?, message = ?, started_at = ?, next_attempt_at = ?
            WHERE id = ?
            """,
            (
                "queued",
                code,
                f"Retry scheduled after provider failure: {message}",
                None,
                (now_dt + timedelta(seconds=backoff_seconds)).isoformat(),
                job_id,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE market_scan_snapshots
            SET status = ?, error_code = ?, message = ?, completed_at = ?, next_attempt_at = ?
            WHERE id = ?
            """,
            ("dead_letter", code, message, now_dt.isoformat(), None, job_id),
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


def _decode_market_scan_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for source_key, target_key, fallback in (
        ("report_json", "report", None),
        ("selected_json", "selected", []),
        ("provider_metadata_json", "provider_metadata", {}),
        ("failures_json", "failures", []),
    ):
        raw_value = data.pop(source_key, None)
        data[target_key] = _json_value(raw_value, fallback)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
    return data


def _json_value(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _iso_value(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _age_seconds(value: Any) -> float:
    if not value:
        return 0.0
    try:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        return 0.0


def validate_job_limit(value: int) -> int:
    if value < 1 or value > 100:
        raise ValidationError("Job worker limit must be between 1 and 100.")
    return value

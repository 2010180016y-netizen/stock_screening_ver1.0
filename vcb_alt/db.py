from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import AppConfig
from .errors import NotFoundError
from .logging_utils import utc_now
from .models import EvaluationResult
from .security import redact_dict, redact_text
from .validation import validate_ticker, validate_tickers


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class PostgresConnection:
    dialect = "postgresql"

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            if exc_type is None:
                self.raw.commit()
            else:
                self.raw.rollback()
            return False
        finally:
            self.raw.close()

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        return self.raw.execute(_postgres_sql(sql), tuple(params or ()))

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    archetype_hint TEXT,
    notes TEXT,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    primary_archetype TEXT NOT NULL,
    combined_score INTEGER NOT NULL,
    setup_strength TEXT NOT NULL,
    can_enter INTEGER NOT NULL,
    suggested_size_pct REAL NOT NULL,
    stop_loss REAL NOT NULL,
    result_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_ticker_time
ON evaluations(ticker, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_time
ON operation_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS failed_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    error_code TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_failed_jobs_time
ON failed_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS provider_alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    recovery TEXT,
    metadata_json TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_time
ON provider_alert_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_provider_time
ON provider_alert_events(provider, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_tenant_time
ON provider_alert_events(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    bucket_key TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_events_key_time
ON rate_limit_events(bucket_key, created_at);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    user_id TEXT,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    request_json TEXT,
    result_json TEXT,
    error_code TEXT,
    message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_time
ON scan_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS market_scan_snapshots (
    id TEXT PRIMARY KEY,
    scan_key TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    report_json TEXT,
    selected_json TEXT,
    provider_metadata_json TEXT,
    failures_json TEXT,
    error_code TEXT,
    message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    expires_at TEXT,
    next_attempt_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_market_scan_snapshots_key_time
ON market_scan_snapshots(scan_key, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_scan_snapshots_status_time
ON market_scan_snapshots(status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_scan_snapshots_active
ON market_scan_snapshots(scan_key)
WHERE status IN ('queued', 'running');
"""


POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker TEXT PRIMARY KEY,
    archetype_hint TEXT,
    notes TEXT,
    added_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    primary_archetype TEXT NOT NULL,
    combined_score INTEGER NOT NULL,
    setup_strength TEXT NOT NULL,
    can_enter INTEGER NOT NULL,
    suggested_size_pct DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION NOT NULL,
    result_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_ticker_time
ON evaluations(ticker, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_time
ON operation_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS failed_jobs (
    id BIGSERIAL PRIMARY KEY,
    command TEXT NOT NULL,
    error_code TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_failed_jobs_time
ON failed_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS provider_alert_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    recovery TEXT,
    metadata_json TEXT,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_time
ON provider_alert_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_provider_time
ON provider_alert_events(provider, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_alert_events_tenant_time
ON provider_alert_events(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    bucket_key TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_events_key_time
ON rate_limit_events(bucket_key, created_at);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    user_id TEXT,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    request_json TEXT,
    result_json TEXT,
    error_code TEXT,
    message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_time
ON scan_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS market_scan_snapshots (
    id TEXT PRIMARY KEY,
    scan_key TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    report_json TEXT,
    selected_json TEXT,
    provider_metadata_json TEXT,
    failures_json TEXT,
    error_code TEXT,
    message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_market_scan_snapshots_key_time
ON market_scan_snapshots(scan_key, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_scan_snapshots_status_time
ON market_scan_snapshots(status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_scan_snapshots_active
ON market_scan_snapshots(scan_key)
WHERE status IN ('queued', 'running');
"""


def connect(config: AppConfig) -> Any:
    if config.database_backend == "postgresql":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL DATABASE_URL requires psycopg[binary]. Run dependency install before startup.") from exc
        return PostgresConnection(psycopg.connect(config.database_url, row_factory=dict_row))
    db_path = config.database_path
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(POSTGRES_SCHEMA_SQL if _is_postgres(conn) else SCHEMA_SQL)
    _ensure_provider_alert_tenant_column(conn)
    conn.commit()


def ensure_initialized(conn: sqlite3.Connection) -> None:
    if _is_postgres(conn):
        row = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ?",
            ("watchlist",),
        ).fetchone()
        if row is None:
            raise NotFoundError("Database is not initialized. Run: python -m vcb_alt init-db")
        _ensure_provider_alert_tenant_column(conn)
        return
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'watchlist'"
    ).fetchone()
    if row is None:
        raise NotFoundError("Database is not initialized. Run: python -m vcb_alt init-db")
    _ensure_provider_alert_tenant_column(conn)


def _ensure_provider_alert_tenant_column(conn: sqlite3.Connection) -> None:
    if _is_postgres(conn):
        conn.execute("ALTER TABLE provider_alert_events ADD COLUMN IF NOT EXISTS tenant_id TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_alert_events_tenant_time
            ON provider_alert_events(tenant_id, created_at DESC)
            """
        )
        return
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(provider_alert_events)").fetchall()
        if "name" in row.keys()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE provider_alert_events ADD COLUMN tenant_id TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_alert_events_tenant_time
        ON provider_alert_events(tenant_id, created_at DESC)
        """
    )


def add_watchlist(conn: sqlite3.Connection, ticker_values: Iterable[str], archetype_hint: str | None = None) -> dict[str, Any]:
    ensure_initialized(conn)
    tickers = validate_tickers(ticker_values)
    added: list[str] = []
    existing: list[str] = []
    now = utc_now()
    for ticker in tickers:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO watchlist (ticker, archetype_hint, notes, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (ticker, archetype_hint, None, now),
        )
        if cursor.rowcount:
            added.append(ticker)
        else:
            existing.append(ticker)
    conn.commit()
    return {"added": added, "existing": existing}


def seed_watchlist(conn: sqlite3.Connection, tickers: Iterable[str]) -> dict[str, Any]:
    return add_watchlist(conn, tickers)


def remove_watchlist(conn: sqlite3.Connection, ticker_values: Iterable[str]) -> dict[str, Any]:
    ensure_initialized(conn)
    tickers = validate_tickers(ticker_values)
    removed: list[str] = []
    missing: list[str] = []
    for ticker in tickers:
        cursor = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        if cursor.rowcount:
            removed.append(ticker)
        else:
            missing.append(ticker)
    conn.commit()
    return {"removed": removed, "missing": missing}


def list_watchlist(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_initialized(conn)
    rows = conn.execute(
        "SELECT ticker, archetype_hint, notes, added_at FROM watchlist ORDER BY ticker"
    ).fetchall()
    return [dict(row) for row in rows]


def save_evaluation(conn: sqlite3.Connection, result: EvaluationResult) -> None:
    ensure_initialized(conn)
    payload = result.to_dict()
    conn.execute(
        """
        INSERT INTO evaluations (
            ticker, evaluated_at, primary_archetype, combined_score, setup_strength,
            can_enter, suggested_size_pct, stop_loss, result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.ticker,
            utc_now(),
            result.primary_archetype,
            result.combined_score,
            result.setup_strength,
            1 if result.can_enter else 0,
            result.suggested_size_pct,
            result.stop_loss,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


def log_operation(
    conn: sqlite3.Connection,
    action: str,
    status: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_initialized(conn)
    conn.execute(
        """
        INSERT INTO operation_logs (action, status, message, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            action,
            status,
            message,
            json.dumps(redact_dict(metadata or {}), ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )
    conn.commit()


def record_failure(
    conn: sqlite3.Connection,
    command: str,
    error_code: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_initialized(conn)
    conn.execute(
        """
        INSERT INTO failed_jobs (command, error_code, message, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            command,
            error_code,
            message,
            json.dumps(redact_dict(metadata or {}), ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )
    conn.commit()


def record_provider_alert(
    conn: sqlite3.Connection,
    provider: str,
    event_type: str,
    severity: str,
    code: str,
    message: str,
    *,
    recovery: str = "",
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> None:
    ensure_initialized(conn)
    conn.execute(
        """
        INSERT INTO provider_alert_events (
            tenant_id, provider, event_type, severity, code, message, recovery, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            str(provider),
            str(event_type),
            str(severity),
            str(code),
            redact_text(str(message)),
            redact_text(str(recovery)),
            json.dumps(redact_dict(metadata or {}), ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )
    conn.commit()


def recent_logs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    ensure_initialized(conn)
    rows = conn.execute(
        """
        SELECT id, action, status, message, metadata_json, created_at
        FROM operation_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_with_json(row) for row in rows]


def recent_failures(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    ensure_initialized(conn)
    rows = conn.execute(
        """
        SELECT id, command, error_code, message, metadata_json, resolved, created_at
        FROM failed_jobs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_with_json(row) for row in rows]


def recent_provider_alerts(
    conn: sqlite3.Connection,
    limit: int = 20,
    *,
    tenant_id: str | None = None,
    include_global: bool = True,
) -> list[dict[str, Any]]:
    ensure_initialized(conn)
    where = ""
    params: tuple[Any, ...]
    if tenant_id is not None:
        where = "WHERE tenant_id = ?"
        params = (tenant_id, limit)
    elif not include_global:
        where = "WHERE tenant_id IS NOT NULL"
        params = (limit,)
    else:
        params = (limit,)
    rows = conn.execute(
        f"""
        SELECT id, tenant_id, provider, event_type, severity, code, message, recovery,
               metadata_json, resolved, created_at
        FROM provider_alert_events
        {where}
        ORDER BY id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_row_with_json(row) for row in rows]


def export_data(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_initialized(conn)
    export: dict[str, Any] = {}
    for table in ("watchlist", "evaluations", "operation_logs", "failed_jobs", "provider_alert_events"):
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        export[table] = [_row_with_json(row) for row in rows]
    return export


def delete_local_data(conn: sqlite3.Connection) -> dict[str, int]:
    ensure_initialized(conn)
    deleted: dict[str, int] = {}
    for table in ("evaluations", "operation_logs", "failed_jobs", "provider_alert_events", "watchlist"):
        cursor = conn.execute(f"DELETE FROM {table}")
        deleted[table] = cursor.rowcount if cursor.rowcount is not None else 0
    conn.commit()
    return deleted


def _row_with_json(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "metadata_json" in data:
        data["metadata"] = _decode_json_field(data.pop("metadata_json"), {})
    if "result_json" in data:
        data["result"] = _decode_json_field(data.pop("result_json"), {})
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
    return data


def _decode_json_field(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    validate_ticker("SAFE")  # keeps validation module imported in packaging smoke checks
    allowed = {
        "watchlist",
        "evaluations",
        "operation_logs",
        "failed_jobs",
        "provider_alert_events",
        "rate_limit_events",
        "scan_jobs",
        "market_scan_snapshots",
    }
    if table not in allowed:
        raise NotFoundError("Unknown table.")
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def _is_postgres(conn: Any) -> bool:
    return getattr(conn, "dialect", "") == "postgresql"


def _postgres_sql(sql: str) -> str:
    transformed = sql.strip()
    if transformed.upper().startswith("INSERT OR IGNORE"):
        transformed = transformed.replace("INSERT OR IGNORE", "INSERT", 1)
        transformed = transformed.rstrip(";") + " ON CONFLICT DO NOTHING"
    transformed = transformed.replace("?", "%s")
    return transformed


def _split_sql_script(script: str) -> list[str]:
    without_comments = re.sub(r"--.*", "", script)
    return [part.strip() for part in without_comments.split(";") if part.strip()]

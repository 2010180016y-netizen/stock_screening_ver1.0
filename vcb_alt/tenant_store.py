from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .auth import hash_password, hash_token, new_session_token, normalize_email, public_user, verify_password
from .errors import ConflictError, ForbiddenError, UnauthorizedError
from .logging_utils import utc_now
from .models import EvaluationResult
from .validation import validate_ticker, validate_tickers


SAAS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_tenant
ON users(tenant_id);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_token
ON sessions(token_hash);

CREATE TABLE IF NOT EXISTS tenant_watchlist (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    notes TEXT,
    added_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, user_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_tenant_watchlist_user
ON tenant_watchlist(tenant_id, user_id, ticker);

CREATE TABLE IF NOT EXISTS tenant_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    combined_score INTEGER NOT NULL,
    public_label TEXT NOT NULL,
    result_json TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tenant_evaluations_latest
ON tenant_evaluations(tenant_id, user_id, ticker, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_time
ON audit_events(tenant_id, created_at DESC);
"""


SAAS_POSTGRES_SCHEMA_SQL = SAAS_SCHEMA_SQL.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "id BIGSERIAL PRIMARY KEY",
).replace(
    "evaluated_at TEXT NOT NULL",
    "evaluated_at TIMESTAMPTZ NOT NULL",
).replace(
    "created_at TEXT NOT NULL\n);",
    "created_at TIMESTAMPTZ NOT NULL\n);",
)


def init_saas_db(conn: sqlite3.Connection) -> None:
    if getattr(conn, "dialect", "") == "postgresql":
        # Vercel can cold-start several Python workers at once. PostgreSQL's
        # CREATE TABLE IF NOT EXISTS is not fully race-free for BIGSERIAL
        # sequence creation, so serialize SaaS schema initialization.
        conn.execute("SELECT pg_advisory_xact_lock(?)", (747265140001,))
    conn.executescript(SAAS_POSTGRES_SCHEMA_SQL if getattr(conn, "dialect", "") == "postgresql" else SAAS_SCHEMA_SQL)
    conn.commit()


def create_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    tenant_name: str = "Default tenant",
    role: str = "owner",
) -> dict[str, Any]:
    safe_email = normalize_email(email)
    now = utc_now()
    tenant_id = _new_id("tenant")
    user_id = _new_id("user")
    try:
        conn.execute("INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)", (tenant_id, tenant_name, now))
        conn.execute(
            """
            INSERT INTO users (id, tenant_id, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, tenant_id, safe_email, hash_password(password), role, now),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if not _is_integrity_error(exc):
            raise
        raise ConflictError("User already exists.") from exc
    return {"id": user_id, "tenant_id": tenant_id, "email": safe_email, "role": role}


def login_user(conn: sqlite3.Connection, *, email: str, password: str) -> dict[str, Any]:
    safe_email = normalize_email(email)
    row = conn.execute(
        "SELECT id, tenant_id, email, password_hash, role FROM users WHERE email = ?",
        (safe_email,),
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise UnauthorizedError("Invalid email or password.")
    token = create_session(conn, dict(row))
    return {"session_token": token, "user": public_user(dict(row))}


def create_session(conn: sqlite3.Connection, user: dict[str, Any], *, ttl_hours: int = 8) -> str:
    token = new_session_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ttl_hours)
    conn.execute(
        """
        INSERT INTO sessions (id, tenant_id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("session"),
            user["tenant_id"],
            user["id"],
            hash_token(token),
            expires_at.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    return token


def authenticate_session(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    if not token:
        raise UnauthorizedError("User session is required.")
    row = conn.execute(
        """
        SELECT users.id, users.tenant_id, users.email, users.role, sessions.expires_at
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ?
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        raise UnauthorizedError("Invalid session.")
    data = dict(row)
    expires_at = _session_expires_at(data.pop("expires_at"))
    if expires_at <= datetime.now(timezone.utc):
        raise UnauthorizedError("Session expired.")
    return data


def require_user(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    user = authenticate_session(conn, token)
    if not user.get("tenant_id"):
        raise ForbiddenError("Tenant context is required.")
    return user


def require_role(user: dict[str, Any], allowed_roles: set[str]) -> dict[str, Any]:
    if str(user.get("role") or "") not in allowed_roles:
        raise ForbiddenError("This action requires elevated permissions.")
    return user


def list_tenant_users(conn: sqlite3.Connection, actor: dict[str, Any]) -> list[dict[str, Any]]:
    require_role(actor, {"owner", "admin"})
    rows = conn.execute(
        """
        SELECT id, email, role, created_at
        FROM users
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        """,
        (actor["tenant_id"],),
    ).fetchall()
    return [dict(row) for row in rows]


def add_user_watchlist(conn: sqlite3.Connection, user: dict[str, Any], ticker_values: list[str]) -> dict[str, Any]:
    tickers = validate_tickers(ticker_values)
    added: list[str] = []
    existing: list[str] = []
    now = utc_now()
    for ticker in tickers:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO tenant_watchlist (tenant_id, user_id, ticker, notes, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["tenant_id"], user["id"], ticker, None, now),
        )
        if cursor.rowcount:
            added.append(ticker)
        else:
            existing.append(ticker)
    conn.commit()
    return {"added": added, "existing": existing}


def list_user_watchlist(conn: sqlite3.Connection, user: dict[str, Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ticker, notes, added_at
        FROM tenant_watchlist
        WHERE tenant_id = ? AND user_id = ?
        ORDER BY ticker
        """,
        (user["tenant_id"], user["id"]),
    ).fetchall()
    return [dict(row) for row in rows]


def remove_user_watchlist(conn: sqlite3.Connection, user: dict[str, Any], ticker_value: str) -> dict[str, Any]:
    ticker = validate_ticker(ticker_value)
    cursor = conn.execute(
        """
        DELETE FROM tenant_watchlist
        WHERE tenant_id = ? AND user_id = ? AND ticker = ?
        """,
        (user["tenant_id"], user["id"], ticker),
    )
    conn.commit()
    return {"removed": [ticker] if cursor.rowcount else [], "missing": [] if cursor.rowcount else [ticker]}


def export_user_data(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    watchlist = list_user_watchlist(conn, user)
    evaluations = [
        _row_with_json(row, "result_json", "result")
        for row in conn.execute(
            """
            SELECT ticker, scoring_version, combined_score, public_label, result_json, evaluated_at
            FROM tenant_evaluations
            WHERE tenant_id = ? AND user_id = ?
            ORDER BY evaluated_at DESC
            """,
            (user["tenant_id"], user["id"]),
        ).fetchall()
    ]
    jobs = [
        _row_with_json(row, "request_json", "request")
        for row in conn.execute(
            """
            SELECT id, status, request_json, result_json, error_code, message, attempts, created_at, started_at, finished_at
            FROM scan_jobs
            WHERE tenant_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (user["tenant_id"], user["id"]),
        ).fetchall()
    ]
    for job in jobs:
        if "result_json" in job:
            job["result"] = _json_value(job.pop("result_json"), {})
    record_audit_event(conn, user, "user.export", "user", user["id"], {"watchlist": len(watchlist)}, commit=False)
    conn.commit()
    return {
        "user": public_user(user),
        "watchlist": watchlist,
        "evaluations": evaluations,
        "jobs": jobs,
    }


def delete_user_account(conn: sqlite3.Connection, user: dict[str, Any], confirm: str) -> dict[str, Any]:
    if confirm != "DELETE_MY_ACCOUNT":
        raise ForbiddenError("Account deletion requires confirm=DELETE_MY_ACCOUNT.")
    record_audit_event(conn, user, "user.delete", "user", user["id"], {}, commit=False)
    deleted: dict[str, int] = {}
    for table in ("sessions", "tenant_evaluations", "scan_jobs", "tenant_watchlist"):
        cursor = conn.execute(
            f"DELETE FROM {table} WHERE tenant_id = ? AND user_id = ?",
            (user["tenant_id"], user["id"]),
        )
        deleted[table] = cursor.rowcount if cursor.rowcount is not None else 0
    cursor = conn.execute("DELETE FROM users WHERE tenant_id = ? AND id = ?", (user["tenant_id"], user["id"]))
    deleted["users"] = cursor.rowcount if cursor.rowcount is not None else 0
    remaining = conn.execute("SELECT COUNT(*) AS count FROM users WHERE tenant_id = ?", (user["tenant_id"],)).fetchone()
    if int(remaining["count"]) == 0:
        cursor = conn.execute("DELETE FROM tenants WHERE id = ?", (user["tenant_id"],))
        deleted["tenants"] = cursor.rowcount if cursor.rowcount is not None else 0
    conn.commit()
    return {"deleted": deleted}


def save_user_evaluation(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    result: EvaluationResult,
    *,
    commit: bool = True,
) -> None:
    payload = result.to_dict()
    conn.execute(
        """
        INSERT INTO tenant_evaluations (
            tenant_id, user_id, ticker, scoring_version, combined_score,
            public_label, result_json, evaluated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["tenant_id"],
            user["id"],
            result.ticker,
            result.scoring_version,
            result.combined_score,
            result.public_label,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )
    if commit:
        conn.commit()


def record_audit_event(
    conn: sqlite3.Connection,
    actor: dict[str, Any],
    action: str,
    target_type: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
    *,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (tenant_id, actor_user_id, action, target_type, target_id, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor["tenant_id"],
            actor["id"],
            action,
            target_type,
            target_id,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            utc_now(),
        ),
    )
    if commit:
        conn.commit()


def list_audit_events(conn: sqlite3.Connection, actor: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    require_role(actor, {"owner", "admin"})
    rows = conn.execute(
        """
        SELECT id, actor_user_id, action, target_type, target_id, metadata_json, created_at
        FROM audit_events
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (actor["tenant_id"], limit),
    ).fetchall()
    return [_row_with_json(row, "metadata_json", "metadata") for row in rows]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _row_with_json(row: Any, source_key: str, target_key: str) -> dict[str, Any]:
    data = dict(row)
    if source_key in data:
        data[target_key] = _json_value(data.pop(source_key), {})
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _json_value(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _session_expires_at(value: Any) -> datetime:
    expires_at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc)


def _is_integrity_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ in {"IntegrityError", "UniqueViolation"}

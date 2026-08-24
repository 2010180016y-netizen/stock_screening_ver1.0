"""Per-request rate limiting for the web layer.

Traffic is bucketed by identity first and client IP second, and each route group gets
its own bucket so that signup bursts, authenticated tenant calls, worker triggers and
anonymous API reads cannot starve one another.

Split out of web.py; behaviour is unchanged.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from typing import Any

from .auth import hash_token
from .config import AppConfig
from .db import connect, init_db
from .errors import AppError
from .rate_limit import DatabaseRateLimiter, InMemoryRateLimiter
from .tenant_store import authenticate_session
from .web_auth import bearer_token, has_valid_worker_token, is_tenant_authenticated_path

API_RATE_LIMITER = InMemoryRateLimiter()
DB_RATE_LIMITER = DatabaseRateLimiter()


def allow_request(handler: BaseHTTPRequestHandler, config: AppConfig, method: str, path: str) -> bool:
    if config.rate_limit_backend == "database":
        with connect(config) as conn:
            init_db(conn)
            key, limit = rate_limit_bucket(handler, config, method, path, conn)
            return DB_RATE_LIMITER.allow(conn, key, limit)
    key, limit = rate_limit_bucket(handler, config, method, path, None)
    return API_RATE_LIMITER.allow(key, limit)


def rate_limit_bucket(
    handler: BaseHTTPRequestHandler,
    config: AppConfig,
    method: str,
    path: str,
    conn: Any | None,
) -> tuple[str, int]:
    headers = dict(handler.headers)
    ip = client_ip(handler, config)
    route_group = rate_limit_route_group(method, path)
    if path == "/api/admin/run-worker" and has_valid_worker_token(config, handler.path, headers):
        return ("worker:run", config.worker_rate_limit_per_minute)
    if config.user_auth_enabled and is_tenant_authenticated_path(path):
        token = bearer_token(headers)
        if token:
            user = rate_limit_user_from_token(conn, token)
            if user:
                return (
                    f"user:{user['tenant_id']}:{user['id']}:{route_group}",
                    config.user_rate_limit_per_minute,
                )
            if conn is None:
                return (f"session:{hash_token(token)[:24]}:{route_group}", config.user_rate_limit_per_minute)
    # Login gets its own, much tighter bucket. Sharing one with registration meant a
    # limit sized for signup bursts (2000/min) also allowed ~33 password guesses per
    # second per IP, which is no brute-force protection at all.
    if path == "/api/auth/login":
        return (f"ip:{ip}:login", config.login_rate_limit_per_minute)
    if path == "/api/auth/register":
        return (f"ip:{ip}:auth", config.auth_rate_limit_per_minute)
    return (f"ip:{ip}:{route_group}", config.rate_limit_per_minute)


def client_ip(handler: BaseHTTPRequestHandler, config: AppConfig) -> str:
    forwarded = handler.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if config.trusted_proxy_headers and forwarded:
        return forwarded
    return handler.client_address[0] if handler.client_address else "unknown"


def rate_limit_route_group(method: str, path: str) -> str:
    if path.startswith("/api/jobs/"):
        return "jobs-read"
    if path == "/api/jobs/scan":
        return "jobs-scan"
    if path == "/api/user/watchlist":
        return f"{method.lower()}:watchlist"
    if path in {"/api/user/scan", "/api/user/select"}:
        return "user-scan"
    if path.startswith("/api/admin/"):
        return "admin"
    if path.startswith("/api/auth/"):
        return "auth"
    return path.removeprefix("/api/") or "api"


def rate_limit_user_from_token(conn: Any | None, token: str) -> dict[str, Any] | None:
    if conn is None:
        return None
    try:
        return authenticate_session(conn, token)
    except AppError:
        return None

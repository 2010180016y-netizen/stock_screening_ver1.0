"""Request authentication for the web layer.

Covers the two independent gates the app uses: the shared deployment access token
that protects the whole site in public mode, and the worker token that protects the
background-scan trigger. Per-user session auth lives in tenant_store.

Split out of web.py; behaviour is unchanged.
"""

from __future__ import annotations

import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import AppConfig
from .errors import UnauthorizedError, ValidationError

# Paths served behind a per-user session token rather than the shared deployment token.
# Both the auth gate and the rate limiter need this set, and they used to keep separate
# copies that had to be edited together.
TENANT_AUTHENTICATED_PATHS = frozenset(
    {
        "/api/me",
        "/api/user/watchlist",
        "/api/user/export",
        "/api/user/account",
        "/api/user/scan",
        "/api/user/select",
        "/api/jobs",
        "/api/jobs/scan",
        "/api/admin/users",
        "/api/admin/audit-events",
        "/api/admin/queue-status",
        "/api/admin/provider-alerts",
    }
)

# Reachable without any token: liveness, and the endpoints used to obtain one.
UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/health",
        "/api/version",
        "/api/auth/register",
        "/api/auth/login",
        "/api/admin/run-worker",
    }
)


def is_tenant_authenticated_path(path: str) -> bool:
    return path in TENANT_AUTHENTICATED_PATHS or path.startswith("/api/jobs/")


def is_authorized(handler: BaseHTTPRequestHandler, config: AppConfig, query: str) -> bool:
    if not config.public_web_enabled:
        return True
    expected = config.web_access_token
    if not expected:
        return False
    candidates: list[str] = []
    query_token = parse_qs(query).get("token", [""])[0]
    if query_token and config.allow_query_token_auth:
        candidates.append(query_token)
    auth_header = handler.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        candidates.append(auth_header[7:].strip())
    cookie_header = handler.headers.get("cookie", "")
    if cookie_header:
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        if "vcb_alt_token" in cookie:
            candidates.append(cookie["vcb_alt_token"].value)
    return any(hmac.compare_digest(candidate, expected) for candidate in candidates)


def auth_cookie_headers(handler: BaseHTTPRequestHandler, config: AppConfig, query: str) -> dict[str, str]:
    if not config.public_web_enabled:
        return {}
    if not config.allow_query_token_auth:
        return {}
    query_token = parse_qs(query).get("token", [""])[0]
    if not query_token or not hmac.compare_digest(query_token, config.web_access_token):
        return {}
    secure_suffix = "; Secure" if is_https_request(handler) else ""
    return {
        "Set-Cookie": f"vcb_alt_token={query_token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800{secure_suffix}",
    }


def is_https_request(handler: BaseHTTPRequestHandler) -> bool:
    forwarded_proto = handler.headers.get("x-forwarded-proto", "")
    if forwarded_proto.lower().split(",", 1)[0].strip() == "https":
        return True
    forwarded_ssl = handler.headers.get("x-forwarded-ssl", "")
    return forwarded_ssl.lower() == "on"


def requires_shared_token(path: str, config: AppConfig) -> bool:
    if not config.public_web_enabled:
        return False
    if path in UNAUTHENTICATED_PATHS:
        return False
    if config.user_auth_enabled and is_tenant_authenticated_path(path):
        return False
    return True


def has_valid_worker_token(config: AppConfig, raw_path: str, headers: dict[str, str]) -> bool:
    if len(config.worker_token) < 16:
        return False
    query = urlparse(raw_path).query
    candidates = worker_token_candidates(config, query, headers)
    return any(hmac.compare_digest(candidate, config.worker_token) for candidate in candidates)


def require_worker_token(config: AppConfig, query: str, headers: dict[str, str]) -> None:
    candidates = worker_token_candidates(config, query, headers)
    if len(config.worker_token) < 16:
        raise ValidationError("Worker token is not configured.")
    if not any(hmac.compare_digest(candidate, config.worker_token) for candidate in candidates):
        raise UnauthorizedError("Worker authentication is required.")


def worker_token_candidates(config: AppConfig, query: str, headers: dict[str, str]) -> list[str]:
    candidates = [
        headers.get("x-vcb-worker-token", ""),
        bearer_token(headers),
    ]
    if config.allow_query_token_auth and not config.production_saas_mode:
        candidates.append(parse_qs(query).get("worker_token", [""])[0])
    return candidates


def production_saas_ready(config: AppConfig) -> bool:
    return (
        config.production_saas_mode
        and config.database_backend == "postgresql"
        and config.user_auth_enabled
        and config.rate_limit_backend == "database"
        and config.scan_queue_enabled
        and len(config.worker_token) >= 16
        and config.worker_cron_enabled
    )


def is_global_operator(config: AppConfig, user: dict[str, Any]) -> bool:
    role = str(user.get("role") or "")
    email = str(user.get("email") or "").lower()
    return role in {"operator", "global_operator"} or email in config.global_operator_emails


def bearer_token(headers: dict[str, str]) -> str:
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""

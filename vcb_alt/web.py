from __future__ import annotations

import json
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import AppConfig, load_config
from .db import connect, init_db, list_watchlist, seed_watchlist
from .errors import AppError, ValidationError
from .models import OperationResult
from .sample_data import SAMPLE_TICKERS
from .tenant_store import init_saas_db
from .web_api import handle_api, _should_auto_seed_watchlist
from .web_auth import (
    auth_cookie_headers,
    bearer_token,
    has_valid_worker_token,
    is_authorized,
    is_global_operator,
    is_https_request,
    is_tenant_authenticated_path,
    production_saas_ready,
    require_worker_token,
    requires_shared_token,
    worker_token_candidates,
)
from .web_ratelimit import (
    allow_request,
    client_ip,
    rate_limit_bucket,
    rate_limit_route_group,
    rate_limit_user_from_token,
)

WEB_ASSET_DIR = Path(__file__).with_name("web_assets")
_WEB_ASSET_CACHE: dict[str, str] = {}

# Backwards-compatible aliases for the private names these helpers had before the split.
_is_authorized = is_authorized
_auth_cookie_headers = auth_cookie_headers
_is_https_request = is_https_request
_requires_shared_token = requires_shared_token
_has_valid_worker_token = has_valid_worker_token
_production_saas_ready = production_saas_ready
_require_worker_token = require_worker_token
_worker_token_candidates = worker_token_candidates
_is_global_operator = is_global_operator
_bearer_token = bearer_token
_is_tenant_authenticated_path = is_tenant_authenticated_path
_allow_request = allow_request
_rate_limit_bucket = rate_limit_bucket
_client_ip = client_ip
_rate_limit_route_group = rate_limit_route_group
_rate_limit_user_from_token = rate_limit_user_from_token


def run_web(host: str = "127.0.0.1", port: int = 8765) -> None:
    config = load_config()
    with connect(config) as conn:
        init_db(conn)
        if config.user_auth_enabled:
            init_saas_db(conn)
        if _should_auto_seed_watchlist(config) and not list_watchlist(conn):
            seed_watchlist(conn, SAMPLE_TICKERS)
    handler = _handler_factory(config)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"VCB-Alt web running at http://{host}:{port}")
    server.serve_forever()


def _handler_factory(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    class VcbAltHandler(BaseHTTPRequestHandler):
        server_version = "VCBAltWeb/0.3"

        def do_GET(self) -> None:
            route_request(self, config, "GET")

        def do_POST(self) -> None:
            route_request(self, config, "POST")

        def do_DELETE(self) -> None:
            route_request(self, config, "DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return VcbAltHandler


def _web_asset(name: str) -> str:
    """Load an extracted UTF-8 web asset.

    These files are the only source of the UI. They ship with the package
    (see package-data in pyproject.toml), so a missing one means a broken install
    rather than a condition worth silently papering over.
    """
    if name in _WEB_ASSET_CACHE:
        return _WEB_ASSET_CACHE[name]
    path = WEB_ASSET_DIR / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError(
            "The web interface could not be loaded.",
            detail=f"Missing web asset '{name}'. Reinstall the vcb_alt package.",
        ) from exc
    _WEB_ASSET_CACHE[name] = text
    return text


def route_request(handler: BaseHTTPRequestHandler, config: AppConfig, method: str) -> None:
    parsed = urlparse(handler.path)
    path = parsed.path
    try:
        if method == "GET" and path == "/assets/app.css":
            _send_text(handler, _web_asset("app.css"), "text/css; charset=utf-8")
            return
        if method == "GET" and path == "/assets/app.js":
            _send_text(handler, _web_asset("app.js"), "application/javascript; charset=utf-8")
            return
        if method == "GET" and path == "/assets/detail.js":
            _send_text(handler, _web_asset("detail.js"), "application/javascript; charset=utf-8")
            return
        if method == "GET" and path == "/favicon.ico":
            _send_text(handler, "", "image/x-icon")
            return
        if method == "GET" and path == "/terms":
            _send_html(handler, _web_asset("terms.html"))
            return
        if method == "GET" and path == "/privacy":
            _send_html(handler, _web_asset("privacy.html"))
            return
        if method == "GET" and path == "/risk-disclosure":
            _send_html(handler, _web_asset("risk-disclosure.html"))
            return
        if method == "GET" and path == "/":
            if config.public_web_enabled and not is_authorized(handler, config, parsed.query):
                _send_html(handler, _web_asset("login.html"), status=HTTPStatus.UNAUTHORIZED)
                return
            headers = auth_cookie_headers(handler, config, parsed.query)
            _send_html(handler, _web_asset("index.html"), extra_headers=headers)
            return
        if method == "GET" and path.startswith("/ticker/"):
            if config.public_web_enabled and not is_authorized(handler, config, parsed.query):
                _send_html(handler, _web_asset("login.html"), status=HTTPStatus.UNAUTHORIZED)
                return
            headers = auth_cookie_headers(handler, config, parsed.query)
            _send_html(handler, _web_asset("detail.html"), extra_headers=headers)
            return
        if path.startswith("/api/"):
            if path != "/api/health" and not allow_request(handler, config, method, path):
                result = OperationResult.failure(
                    "Rate limit exceeded. Try again later.",
                    status_code=429,
                    code="RATE_LIMITED",
                )
                _send_json(handler, result, result.status_code)
                return
            if requires_shared_token(path, config) and not is_authorized(handler, config, parsed.query):
                result = OperationResult.failure(
                    "Authentication is required for public web mode.",
                    status_code=401,
                    code="UNAUTHORIZED",
                )
                _send_json(handler, result, result.status_code)
                return
            result = handle_api(config, method, path, parsed.query, _read_json(handler, config), dict(handler.headers))
            _send_json(handler, result, result.status_code)
            return
        raise ValidationError("Route not found.")
    except AppError as exc:
        _send_json(
            handler,
            OperationResult.failure(exc.message, status_code=exc.status_code, code=exc.code, detail=exc.detail),
            exc.status_code,
        )
    except Exception as exc:
        traceback.print_exception(type(exc), exc, exc.__traceback__, limit=8, file=sys.stderr)
        _send_json(
            handler,
            OperationResult.failure("Unexpected server error.", status_code=500, code="INTERNAL_ERROR"),
            500,
        )


def _read_json(handler: BaseHTTPRequestHandler, config: AppConfig) -> dict[str, Any] | None:
    try:
        length = int(handler.headers.get("content-length", "0") or 0)
    except ValueError as exc:
        raise ValidationError("Invalid Content-Length header.") from exc
    if length <= 0:
        return None
    if length > config.max_json_body_bytes:
        raise ValidationError(f"Request body exceeds {config.max_json_body_bytes} bytes.")
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Request body must be valid JSON.") from exc
    if value is not None and not isinstance(value, dict):
        raise ValidationError("Request JSON body must be an object.")
    return value


def _send_json(handler: BaseHTTPRequestHandler, result: OperationResult, status: int = 200) -> None:
    body = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_html(
    handler: BaseHTTPRequestHandler,
    html: str,
    *,
    status: HTTPStatus = HTTPStatus.OK,
    extra_headers: dict[str, str] | None = None,
) -> None:
    _send_text(handler, html, "text/html; charset=utf-8", status=status, extra_headers=extra_headers)


def _send_text(
    handler: BaseHTTPRequestHandler,
    text: str,
    content_type: str,
    *,
    status: HTTPStatus = HTTPStatus.OK,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

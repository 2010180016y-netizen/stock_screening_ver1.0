from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from vcb_alt.config import load_config
from vcb_alt.db import connect, init_db, list_watchlist, seed_watchlist
from vcb_alt.sample_data import SAMPLE_TICKERS
from vcb_alt.tenant_store import init_saas_db
from vcb_alt.web import route_request


ROOT_DIR = Path(__file__).resolve().parents[1]
_CACHED_CONFIG: Any | None = None
_BOOTSTRAPPED = False


def _configure_serverless_defaults() -> None:
    os.environ.setdefault("VCB_ALT_DATABASE_URL", "sqlite:////tmp/vcb_alt.db")
    os.environ.setdefault("VCB_ALT_DATA_DIR", "/tmp/vcb_alt_data")
    os.environ.setdefault("VCB_ALT_LOG_DIR", "/tmp/vcb_alt_logs")
    os.environ.setdefault("VCB_ALT_AUTO_SEED_SAMPLE", "true")


def _load_runtime_config() -> Any:
    global _CACHED_CONFIG
    if _CACHED_CONFIG is not None:
        return _CACHED_CONFIG
    _configure_serverless_defaults()
    _CACHED_CONFIG = load_config(ROOT_DIR)
    return _CACHED_CONFIG


def _bootstrap_runtime() -> Any:
    global _BOOTSTRAPPED
    config = _load_runtime_config()
    if _BOOTSTRAPPED:
        return config
    with connect(config) as conn:
        init_db(conn)
        if config.user_auth_enabled:
            init_saas_db(conn)
        if config.auto_seed_sample and not list_watchlist(conn):
            seed_watchlist(conn, SAMPLE_TICKERS)
    _BOOTSTRAPPED = True
    return config


def _runtime_for_request(path: str) -> Any:
    if path.split("?", 1)[0] == "/api/health":
        return _load_runtime_config()
    return _bootstrap_runtime()


class handler(BaseHTTPRequestHandler):
    server_version = "VCBAltVercel/0.1"

    def do_GET(self) -> None:
        route_request(self, _runtime_for_request(self.path), "GET")

    def do_POST(self) -> None:
        route_request(self, _runtime_for_request(self.path), "POST")

    def do_DELETE(self) -> None:
        route_request(self, _runtime_for_request(self.path), "DELETE")

    def log_message(self, format: str, *args: Any) -> None:
        return

from __future__ import annotations

import hmac
import json
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from .ai_summary import build_ai_summary
from .auth import hash_token, public_user
from .config import AppConfig, doctor_report, load_config
from .db import (
    add_watchlist,
    connect,
    ensure_initialized,
    init_db,
    list_watchlist,
    log_operation,
    recent_failures,
    recent_logs,
    record_failure,
    remove_watchlist,
    save_evaluation,
    seed_watchlist,
)
from .errors import AppError, ValidationError
from .job_queue import enqueue_scan_job, get_scan_job, list_scan_jobs, queue_status, run_queued_scan_jobs, validate_job_limit
from .market_universe import scan_market_universe
from .models import OperationResult, SCORING_VERSION
from .portfolio import select_portfolio
from .providers import get_price_history, get_snapshot, get_ticker_profile, provider_status
from .rate_limit import DatabaseRateLimiter, InMemoryRateLimiter
from .saas_readiness import get_saas_readiness
from .scoring import evaluate_snapshot
from .sample_data import SAMPLE_TICKERS
from .tenant_store import (
    add_user_watchlist,
    authenticate_session,
    create_user,
    delete_user_account,
    export_user_data,
    init_saas_db,
    list_audit_events,
    list_tenant_users,
    list_user_watchlist,
    login_user,
    require_role,
    remove_user_watchlist,
    require_user,
    save_user_evaluation,
)
from .validation import validate_ticker

_API_RATE_LIMITER = InMemoryRateLimiter()
_DB_RATE_LIMITER = DatabaseRateLimiter()


def run_web(host: str = "127.0.0.1", port: int = 8765) -> None:
    config = load_config()
    with connect(config) as conn:
        init_db(conn)
        if config.user_auth_enabled:
            init_saas_db(conn)
        if config.auto_seed_sample and not list_watchlist(conn):
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


def route_request(handler: BaseHTTPRequestHandler, config: AppConfig, method: str) -> None:
    parsed = urlparse(handler.path)
    path = parsed.path
    try:
        if method == "GET" and path == "/assets/app.css":
            _send_text(handler, APP_CSS, "text/css; charset=utf-8")
            return
        if method == "GET" and path == "/assets/app.js":
            _send_text(handler, _dashboard_js(), "application/javascript; charset=utf-8")
            return
        if method == "GET" and path == "/assets/detail.js":
            _send_text(handler, _detail_js(), "application/javascript; charset=utf-8")
            return
        if method == "GET" and path == "/favicon.ico":
            _send_text(handler, "", "image/x-icon")
            return
        if method == "GET" and path == "/terms":
            _send_html(handler, TERMS_HTML)
            return
        if method == "GET" and path == "/privacy":
            _send_html(handler, PRIVACY_HTML)
            return
        if method == "GET" and path == "/risk-disclosure":
            _send_html(handler, RISK_DISCLOSURE_HTML)
            return
        if method == "GET" and path == "/":
            if config.public_web_enabled and not _is_authorized(handler, config, parsed.query):
                _send_html(handler, LOGIN_HTML, status=HTTPStatus.UNAUTHORIZED)
                return
            headers = _auth_cookie_headers(handler, config, parsed.query)
            _send_html(handler, INDEX_HTML, extra_headers=headers)
            return
        if method == "GET" and path.startswith("/ticker/"):
            if config.public_web_enabled and not _is_authorized(handler, config, parsed.query):
                _send_html(handler, LOGIN_HTML, status=HTTPStatus.UNAUTHORIZED)
                return
            headers = _auth_cookie_headers(handler, config, parsed.query)
            _send_html(handler, DETAIL_HTML, extra_headers=headers)
            return
        if path.startswith("/api/"):
            if path != "/api/health" and not _allow_request(handler, config, method, path):
                result = OperationResult.failure(
                    "Rate limit exceeded. Try again later.",
                    status_code=429,
                    code="RATE_LIMITED",
                )
                _send_json(handler, result, result.status_code)
                return
            if _requires_shared_token(path, config) and not _is_authorized(handler, config, parsed.query):
                result = OperationResult.failure(
                    "Authentication is required for public web mode.",
                    status_code=401,
                    code="UNAUTHORIZED",
                )
                _send_json(handler, result, result.status_code)
                return
            result = handle_api(config, method, path, parsed.query, _read_json(handler), dict(handler.headers))
            _send_json(handler, result, result.status_code)
            return
        raise ValidationError("Route not found.")
    except AppError as exc:
        _send_json(
            handler,
            OperationResult.failure(exc.message, status_code=exc.status_code, code=exc.code, detail=exc.detail),
            exc.status_code,
        )
    except Exception:
        _send_json(
            handler,
            OperationResult.failure("Unexpected server error.", status_code=500, code="INTERNAL_ERROR"),
            500,
        )


def handle_api(
    config: AppConfig,
    method: str,
    path: str,
    query: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str] | None = None,
) -> OperationResult:
    if method == "GET" and path == "/api/health":
        return OperationResult.success("OK", {"status": "healthy"})
    if method == "GET" and path == "/api/config":
        return OperationResult.success("Configuration loaded.", doctor_report(config))
    if method == "GET" and path == "/api/provider-status":
        return OperationResult.success("Provider status loaded.", provider_status(config))
    if method == "GET" and path == "/api/release-status":
        return OperationResult.success("Release status loaded.", _release_status(config))
    if method == "GET" and path == "/api/ticker-analysis":
        ticker = parse_qs(query).get("ticker", [""])[0]
        return OperationResult.success("Ticker analysis loaded.", _ticker_analysis(config, ticker))
    if method == "GET" and path == "/api/saas-readiness":
        return OperationResult.success("SaaS readiness checked.", get_saas_readiness())
    if method in {"GET", "POST"} and path == "/api/admin/run-worker":
        if not config.worker_cron_enabled:
            return OperationResult.success("Worker cron is disabled.", {"processed": 0, "failed": 0, "disabled": True})
        _require_worker_token(config, query, headers or {})
        if not config.scan_queue_enabled:
            raise ValidationError("Scan queue is not enabled.")
        limit = int(parse_qs(query).get("limit", ["10"])[0])
        with connect(config) as conn:
            ensure_initialized(conn)
            if config.user_auth_enabled:
                init_saas_db(conn)
            return OperationResult.success(
                "Worker run completed.",
                run_queued_scan_jobs(config, conn, limit=validate_job_limit(limit)),
            )

    with connect(config) as conn:
        ensure_initialized(conn)
        if config.user_auth_enabled:
            init_saas_db(conn)
        if method == "POST" and path == "/api/auth/register":
            if not config.user_auth_enabled or not config.user_registration_enabled:
                raise ValidationError("User registration is not enabled.")
            body = payload or {}
            user = create_user(
                conn,
                email=str(body.get("email", "")),
                password=str(body.get("password", "")),
                tenant_name=str(body.get("tenant_name") or "Default tenant"),
            )
            session = login_user(conn, email=user["email"], password=str(body.get("password", "")))
            return OperationResult.success("User registered.", session, status_code=201)
        if method == "POST" and path == "/api/auth/login":
            if not config.user_auth_enabled:
                raise ValidationError("User authentication is not enabled.")
            body = payload or {}
            return OperationResult.success(
                "Logged in.",
                login_user(conn, email=str(body.get("email", "")), password=str(body.get("password", ""))),
            )
        if method == "GET" and path == "/api/me":
            user = require_user(conn, _bearer_token(headers or {}))
            return OperationResult.success("User loaded.", public_user(user))
        if method == "GET" and path == "/api/user/export":
            user = require_user(conn, _bearer_token(headers or {}))
            return OperationResult.success("User data exported.", export_user_data(conn, user))
        if method == "DELETE" and path == "/api/user/account":
            user = require_user(conn, _bearer_token(headers or {}))
            confirm = parse_qs(query).get("confirm", [""])[0]
            return OperationResult.success("User account deleted.", delete_user_account(conn, user, confirm))
        if path == "/api/user/watchlist":
            user = require_user(conn, _bearer_token(headers or {}))
            if method == "GET":
                items = list_user_watchlist(conn, user)
                return OperationResult.success("User watchlist loaded.", {"items": items, "count": len(items)})
            if method == "POST":
                body = payload or {}
                raw = body.get("tickers") or body.get("ticker")
                tickers = raw.replace(",", " ").split() if isinstance(raw, str) else [str(item) for item in raw or []]
                return OperationResult.success(
                    "User watchlist updated.",
                    add_user_watchlist(conn, user, tickers),
                    status_code=201,
                )
            if method == "DELETE":
                ticker = parse_qs(query).get("ticker", [""])[0]
                return OperationResult.success("User watchlist updated.", remove_user_watchlist(conn, user, ticker))
        if path == "/api/jobs/scan" and method == "POST":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, _bearer_token(headers or {}))
            return OperationResult.success("Scan job queued.", enqueue_scan_job(conn, user), status_code=202)
        if path == "/api/user/scan" and method in {"GET", "POST"}:
            if not config.user_auth_enabled:
                raise ValidationError("User authentication is not enabled.")
            user = require_user(conn, _bearer_token(headers or {}))
            return _scan_user(config, conn, user)
        if path == "/api/user/select" and method in {"GET", "POST"}:
            if not config.user_auth_enabled:
                raise ValidationError("User authentication is not enabled.")
            user = require_user(conn, _bearer_token(headers or {}))
            if config.scan_mode == "market_universe":
                return _scan_user(config, conn, user, message="Selection completed.")
            evaluations, failures, elapsed_ms = _evaluate_user_watchlist(config, conn, user)
            selection = select_portfolio(evaluations)
            return OperationResult.success(
                "Selection completed.",
                {"selection": selection.to_dict(), "failures": failures, "elapsed_ms": elapsed_ms},
            )
        if path == "/api/jobs" and method == "GET":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, _bearer_token(headers or {}))
            jobs = list_scan_jobs(conn, user)
            return OperationResult.success("Scan jobs loaded.", {"items": jobs, "count": len(jobs)})
        if path.startswith("/api/jobs/") and method == "GET":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, _bearer_token(headers or {}))
            job_id = path.removeprefix("/api/jobs/")
            return OperationResult.success("Scan job loaded.", get_scan_job(conn, user, job_id))
        if method == "GET" and path == "/api/admin/users":
            user = require_role(require_user(conn, _bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Tenant users loaded.", {"items": list_tenant_users(conn, user)})
        if method == "GET" and path == "/api/admin/audit-events":
            user = require_role(require_user(conn, _bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Audit events loaded.", {"items": list_audit_events(conn, user)})
        if method == "GET" and path == "/api/admin/queue-status":
            user = require_role(require_user(conn, _bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Queue status loaded.", queue_status(conn, user["tenant_id"]))
        if config.user_auth_enabled and path in {"/api/watchlist", "/api/scan", "/api/select"}:
            raise ValidationError("Use tenant-scoped authenticated APIs in SaaS mode.")
        if method == "GET" and path == "/api/watchlist":
            items = list_watchlist(conn)
            return OperationResult.success("Watchlist loaded.", {"items": items, "count": len(items)})
        if method == "POST" and path == "/api/watchlist":
            body = payload or {}
            raw = body.get("tickers") or body.get("ticker")
            if isinstance(raw, str):
                tickers = raw.replace(",", " ").split()
            elif isinstance(raw, list):
                tickers = [str(item) for item in raw]
            else:
                raise ValidationError("ticker or tickers is required.")
            data = add_watchlist(conn, tickers)
            log_operation(conn, "web watchlist add", "success", "Watchlist updated.", data)
            return OperationResult.success("Watchlist updated.", data, status_code=201)
        if method == "DELETE" and path == "/api/watchlist":
            ticker = parse_qs(query).get("ticker", [""])[0]
            data = remove_watchlist(conn, [validate_ticker(ticker)])
            log_operation(conn, "web watchlist remove", "success", "Watchlist updated.", data)
            return OperationResult.success("Watchlist updated.", data)
        if method == "GET" and path == "/api/scan":
            return _scan(config, conn)
        if method == "GET" and path == "/api/select":
            if config.scan_mode == "market_universe":
                return _scan(config, conn, message="Selection completed.")
            evaluations, failures, elapsed_ms = _evaluate_watchlist(config, conn, "web select")
            selection = select_portfolio(evaluations)
            log_operation(
                conn,
                "web select",
                "success" if not failures else "partial_success",
                f"Selected {len(selection.selected)} candidates.",
                {"elapsed_ms": elapsed_ms},
            )
            return OperationResult.success(
                "Selection completed.",
                {"selection": selection.to_dict(), "failures": failures, "elapsed_ms": elapsed_ms},
            )
        if method == "GET" and path == "/api/logs":
            items = recent_logs(conn, 12)
            return OperationResult.success("Logs loaded.", {"items": items, "count": len(items)})
        if method == "GET" and path == "/api/failures":
            items = recent_failures(conn, 12)
            return OperationResult.success("Failures loaded.", {"items": items, "count": len(items)})
    raise ValidationError("API route not found.")


def _scan(config: AppConfig, conn: Any, *, message: str = "Scan completed.") -> OperationResult:
    if config.scan_mode == "market_universe":
        report = scan_market_universe(config)
        for result in report.evaluations:
            save_evaluation(conn, result)
        log_operation(
            conn,
            "market universe scan",
            "success" if not report.failures else "partial_success",
            f"Scanned {report.universe.get('count', 0)} market symbols and scored {len(report.evaluations)} candidates.",
            {
                "elapsed_ms": report.elapsed_ms,
                "failures": len(report.failures),
                "prefilter_count": report.prefilter.get("count", 0),
            },
        )
        return OperationResult.success(message, report.to_api_dict())

    evaluations, failures, elapsed_ms = _evaluate_watchlist(config, conn, "web scan")
    status = "success" if not failures else "partial_success"
    log_operation(
        conn,
        "web scan",
        status,
        f"Scanned {len(evaluations)} tickers with {len(failures)} failures.",
        {"elapsed_ms": elapsed_ms, "failures": len(failures)},
    )
    return OperationResult.success(
        "Scan completed.",
        {
            "items": [item.to_dict() for item in evaluations],
            "failures": failures,
            "count": len(evaluations),
            "elapsed_ms": elapsed_ms,
        },
    )


def _scan_user(config: AppConfig, conn: Any, user: dict[str, Any], *, message: str = "Scan completed.") -> OperationResult:
    if config.scan_mode == "market_universe":
        report = scan_market_universe(config)
        for result in report.evaluations:
            save_user_evaluation(conn, user, result, commit=False)
        conn.commit()
        return OperationResult.success(message, report.to_api_dict())
    return _scan_user_watchlist(config, conn, user, message=message)


def _scan_user_watchlist(
    config: AppConfig,
    conn: Any,
    user: dict[str, Any],
    *,
    message: str = "Scan completed.",
) -> OperationResult:
    # The dashboard scan button needs an immediate tenant-scoped result set; queue-backed scans
    # remain available for heavier hosted load, but this path keeps the owner trial UI responsive.
    evaluations, failures, elapsed_ms = _evaluate_user_watchlist(config, conn, user)
    selection = select_portfolio(evaluations)
    return OperationResult.success(
        message,
        {
            "items": [item.to_dict() for item in evaluations],
            "failures": failures,
            "count": len(evaluations),
            "elapsed_ms": elapsed_ms,
            "selection": selection.to_dict(),
        },
    )


def _evaluate_watchlist(config: AppConfig, conn: Any, command: str) -> tuple[list[Any], list[dict[str, Any]], int]:
    start = perf_counter()
    evaluations: list[Any] = []
    failures: list[dict[str, Any]] = []
    for item in list_watchlist(conn):
        ticker = item["ticker"]
        try:
            result = evaluate_snapshot(get_snapshot(config, ticker))
            save_evaluation(conn, result)
            evaluations.append(result)
        except AppError as exc:
            failure = {"ticker": ticker, "code": exc.code, "message": exc.message}
            record_failure(conn, command, exc.code, exc.message, failure)
            failures.append(failure)
    elapsed_ms = int((perf_counter() - start) * 1000)
    return evaluations, failures, elapsed_ms


def _evaluate_user_watchlist(
    config: AppConfig,
    conn: Any,
    user: dict[str, Any],
) -> tuple[list[Any], list[dict[str, Any]], int]:
    start = perf_counter()
    evaluations: list[Any] = []
    failures: list[dict[str, Any]] = []
    for item in list_user_watchlist(conn, user):
        ticker = item["ticker"]
        try:
            result = evaluate_snapshot(get_snapshot(config, ticker))
            # Batch the commit across the full watchlist so a scan avoids one DB commit per ticker.
            save_user_evaluation(conn, user, result, commit=False)
            evaluations.append(result)
        except AppError as exc:
            failures.append({"ticker": ticker, "code": exc.code, "message": exc.message})
    conn.commit()
    elapsed_ms = int((perf_counter() - start) * 1000)
    return evaluations, failures, elapsed_ms


def _release_status(config: AppConfig) -> dict[str, Any]:
    status = provider_status(config)
    live_research_ready = bool(status.get("research_api_configured") or status.get("enrichment_available"))
    live_intraday_ready = bool(
        status.get("intraday_data_provider") == "alpaca" and status.get("intraday_api_configured")
    )
    return {
        "release_channel": "operator_trial",
        "release_label": "Owner pre-user usage build",
        "scoring_version": SCORING_VERSION,
        "user_trial_ready": True,
        "public_launch_ready": False,
        "production_saas_ready": _production_saas_ready(config),
        "public_scope": "Single-operator/token-protected preview, not unrestricted public SaaS.",
        "configured_data": {
            "market_provider": status.get("provider"),
            "research_provider": status.get("research_data_provider"),
            "research_ready": live_research_ready,
            "intraday_provider": status.get("intraday_data_provider"),
            "intraday_ready": live_intraday_ready,
            "ai_summary_provider": status.get("ai_summary_provider"),
            "ai_summary_ready": status.get("ai_summary_configured"),
            "scan_mode": config.scan_mode,
            "market_universe_provider": status.get("market_universe_provider"),
            "market_universe_live_ready": status.get("market_universe_live_ready"),
            "market_prefilter_limit": status.get("market_prefilter_limit"),
            "database_backend": config.database_backend,
            "rate_limit_backend": config.rate_limit_backend,
            "scan_queue_enabled": config.scan_queue_enabled,
            "user_auth_enabled": config.user_auth_enabled,
            "worker_configured": len(config.worker_token) >= 16,
            "worker_cron_enabled": config.worker_cron_enabled,
        },
        "operator_can_use": [
            "Open the token-protected dashboard.",
            "Run all-market discovery from the configured market universe.",
            "Use watchlist tickers as an optional manual research list.",
            "Open ticker detail pages with five-year charts, sector/industry, rationale, and AI summary.",
            "Review provider warnings before treating a candidate as research-complete.",
        ],
        "do_not_publicly_launch_until": [
            "Per-user authentication is enabled with durable sessions.",
            "PostgreSQL or another durable production database is live.",
            "Tenant isolation and production rate limits are deployed.",
            "Licensed live/research provider credentials are configured and monitored.",
            "Legal, risk, privacy, and support workflows are approved.",
            "Hosted load test passes for the target traffic level.",
        ],
        "warnings": status.get("warnings", []),
    }


def _ticker_analysis(config: AppConfig, ticker_value: str) -> dict[str, Any]:
    ticker = validate_ticker(ticker_value)
    snapshot = get_snapshot(config, ticker)
    evaluation = evaluate_snapshot(snapshot)
    # Keep one enriched snapshot per detail request so paid/limited providers are not called twice.
    analysis = {
        "ticker": ticker,
        "evaluation": evaluation.to_dict(),
        "metrics": _snapshot_metrics(snapshot),
        "profile": get_ticker_profile(config, ticker, snapshot=snapshot),
        "history": get_price_history(config, ticker, years=5),
        "expert_consensus": _analysis_consensus(evaluation.to_dict()),
    }
    analysis["ai_summary"] = build_ai_summary(config, analysis)
    return analysis


def _snapshot_metrics(snapshot: Any) -> dict[str, Any]:
    return {
        "return_12w_pct": snapshot.return_12w_pct,
        "return_12m_pct": snapshot.return_12m_pct,
        "drawdown_52w_pct": snapshot.drawdown_52w_pct,
        "price_vs_50dma_pct": snapshot.price_vs_50dma_pct,
        "price_vs_150dma_pct": snapshot.price_vs_150dma_pct,
        "price_vs_200dma_pct": snapshot.price_vs_200dma_pct,
        "trend_template_score": snapshot.trend_template_score,
        "surge_score": snapshot.surge_score,
        "relative_strength_12w_pp": snapshot.sector_rs_12w_pp,
        "breakout_volume_ratio": snapshot.breakout_volume_ratio,
        "earnings_surprise_pct": getattr(snapshot, "earnings_surprise_pct", 0),
        "short_interest_pct": getattr(snapshot, "short_interest_pct", 0),
        "days_to_cover": getattr(snapshot, "days_to_cover", 0),
        "call_open_interest": getattr(snapshot, "call_open_interest", 0),
        "put_open_interest": getattr(snapshot, "put_open_interest", 0),
        "put_call_ratio": getattr(snapshot, "put_call_ratio", 0),
        "analyst_revision_score": getattr(snapshot, "analyst_revision_score", 0),
        "analyst_buy_count": getattr(snapshot, "analyst_buy_count", 0),
        "analyst_hold_count": getattr(snapshot, "analyst_hold_count", 0),
        "analyst_sell_count": getattr(snapshot, "analyst_sell_count", 0),
        "news_headline_count_30d": getattr(snapshot, "news_headline_count_30d", 0),
        "filing_catalyst_30d": getattr(snapshot, "filing_catalyst_30d", False),
        "latest_filing_date": getattr(snapshot, "latest_filing_date", ""),
        "latest_filing_type": getattr(snapshot, "latest_filing_type", ""),
        "latest_filing_url": getattr(snapshot, "latest_filing_url", ""),
        "intraday_price": getattr(snapshot, "intraday_price", 0),
        "intraday_change_pct": getattr(snapshot, "intraday_change_pct", 0),
        "intraday_volume": getattr(snapshot, "intraday_volume", 0),
        "intraday_source": getattr(snapshot, "intraday_source", ""),
        "intraday_as_of": getattr(snapshot, "intraday_as_of", ""),
        "intraday_error": getattr(snapshot, "intraday_error", ""),
        "data_coverage_score": getattr(snapshot, "data_coverage_score", 0),
        "enrichment_source": getattr(snapshot, "enrichment_source", ""),
        "enrichment_as_of": getattr(snapshot, "enrichment_as_of", ""),
    }


def _analysis_consensus(evaluation: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "Quant",
            "title": "Score and trend state",
            "body": (
                f"Combined score is {evaluation['combined_score']} using "
                f"{evaluation['scoring_version']}; review the trend and surge metrics before acting."
            ),
        },
        {
            "role": "Risk",
            "title": "Risk reference",
            "body": "Use the risk reference and allocation guide as review inputs, not trade instructions.",
        },
        {
            "role": "Product",
            "title": "Selection reason",
            "body": "The first rationale bullets explain the main reason this ticker reached the review list.",
        },
    ]


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    length = int(handler.headers.get("content-length", "0") or 0)
    if length <= 0:
        return None
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw:
        return None
    return json.loads(raw)


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


def _is_authorized(handler: BaseHTTPRequestHandler, config: AppConfig, query: str) -> bool:
    if not config.public_web_enabled:
        return True
    expected = config.web_access_token
    if not expected:
        return False
    candidates: list[str] = []
    query_token = parse_qs(query).get("token", [""])[0]
    if query_token:
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


def _auth_cookie_headers(handler: BaseHTTPRequestHandler, config: AppConfig, query: str) -> dict[str, str]:
    if not config.public_web_enabled:
        return {}
    query_token = parse_qs(query).get("token", [""])[0]
    if not query_token or not hmac.compare_digest(query_token, config.web_access_token):
        return {}
    secure_suffix = "; Secure" if _is_https_request(handler) else ""
    return {
        "Set-Cookie": f"vcb_alt_token={query_token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800{secure_suffix}",
    }


def _is_https_request(handler: BaseHTTPRequestHandler) -> bool:
    forwarded_proto = handler.headers.get("x-forwarded-proto", "")
    if forwarded_proto.lower().split(",", 1)[0].strip() == "https":
        return True
    forwarded_ssl = handler.headers.get("x-forwarded-ssl", "")
    return forwarded_ssl.lower() == "on"


def _requires_shared_token(path: str, config: AppConfig) -> bool:
    if not config.public_web_enabled:
        return False
    if path in {"/api/health", "/api/auth/register", "/api/auth/login", "/api/admin/run-worker"}:
        return False
    if config.user_auth_enabled and (
        path in {
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
        }
        or path.startswith("/api/jobs/")
    ):
        return False
    return True


def _allow_request(handler: BaseHTTPRequestHandler, config: AppConfig, method: str, path: str) -> bool:
    if config.rate_limit_backend == "database":
        with connect(config) as conn:
            init_db(conn)
            key, limit = _rate_limit_bucket(handler, config, method, path, conn)
            return _DB_RATE_LIMITER.allow(conn, key, limit)
    key, limit = _rate_limit_bucket(handler, config, method, path, None)
    return _API_RATE_LIMITER.allow(key, limit)


def _rate_limit_bucket(
    handler: BaseHTTPRequestHandler,
    config: AppConfig,
    method: str,
    path: str,
    conn: Any | None,
) -> tuple[str, int]:
    headers = dict(handler.headers)
    ip = _client_ip(handler)
    route_group = _rate_limit_route_group(method, path)
    if path == "/api/admin/run-worker" and _has_valid_worker_token(config, handler.path, headers):
        return ("worker:run", config.worker_rate_limit_per_minute)
    if config.user_auth_enabled and _is_tenant_authenticated_path(path):
        token = _bearer_token(headers)
        if token:
            user = _rate_limit_user_from_token(conn, token)
            if user:
                return (
                    f"user:{user['tenant_id']}:{user['id']}:{route_group}",
                    config.user_rate_limit_per_minute,
                )
            if conn is None:
                return (f"session:{hash_token(token)[:24]}:{route_group}", config.user_rate_limit_per_minute)
    if path in {"/api/auth/register", "/api/auth/login"}:
        return (f"ip:{ip}:auth", config.auth_rate_limit_per_minute)
    return (f"ip:{ip}:{route_group}", config.rate_limit_per_minute)


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return handler.client_address[0] if handler.client_address else "unknown"


def _rate_limit_route_group(method: str, path: str) -> str:
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


def _is_tenant_authenticated_path(path: str) -> bool:
    return (
        path
        in {
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
        }
        or path.startswith("/api/jobs/")
    )


def _rate_limit_user_from_token(conn: Any | None, token: str) -> dict[str, Any] | None:
    if conn is None:
        return None
    try:
        return authenticate_session(conn, token)
    except AppError:
        return None


def _has_valid_worker_token(config: AppConfig, raw_path: str, headers: dict[str, str]) -> bool:
    if len(config.worker_token) < 16:
        return False
    query = urlparse(raw_path).query
    candidates = [
        parse_qs(query).get("worker_token", [""])[0],
        headers.get("x-vcb-worker-token", ""),
        _bearer_token(headers),
    ]
    return any(hmac.compare_digest(candidate, config.worker_token) for candidate in candidates)


def _production_saas_ready(config: AppConfig) -> bool:
    return (
        config.production_saas_mode
        and config.database_backend == "postgresql"
        and config.user_auth_enabled
        and config.rate_limit_backend == "database"
        and config.scan_queue_enabled
        and len(config.worker_token) >= 16
        and config.worker_cron_enabled
    )


def _require_worker_token(config: AppConfig, query: str, headers: dict[str, str]) -> None:
    candidates = [
        parse_qs(query).get("worker_token", [""])[0],
        headers.get("x-vcb-worker-token", ""),
        _bearer_token(headers),
    ]
    if len(config.worker_token) < 16:
        raise ValidationError("Worker token is not configured.")
    if not any(hmac.compare_digest(candidate, config.worker_token) for candidate in candidates):
        from .errors import UnauthorizedError

        raise UnauthorizedError("Worker authentication is required.")


def _bearer_token(headers: dict[str, str]) -> str:
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


_SAFE_APP_JS: str | None = None
_SAFE_DETAIL_JS: str | None = None


def _dashboard_js() -> str:
    global _SAFE_APP_JS
    if _SAFE_APP_JS is None:
        source = _replace_js_ko_block(APP_JS, "const I18N =", APP_KO_I18N)
        _SAFE_APP_JS = _replace_render_scan_i18n(source)
    return _SAFE_APP_JS


def _detail_js() -> str:
    global _SAFE_DETAIL_JS
    if _SAFE_DETAIL_JS is None:
        _SAFE_DETAIL_JS = _replace_js_ko_block(DETAIL_JS, "const DETAIL_I18N =", DETAIL_KO_I18N)
    return _SAFE_DETAIL_JS


def _replace_js_ko_block(source: str, marker: str, replacement: str) -> str:
    start = source.index("  ko: {", source.index(marker))
    end = source.index("\n  }\n};", start) + len("\n  }")
    return source[:start] + replacement + source[end:]


def _replace_render_scan_i18n(source: str) -> str:
    start = source.index("  document.getElementById('actionable-meta').textContent", source.index("function renderScan"))
    end = source.index("  renderTable('actionable-body'", start)
    return source[:start] + APP_RENDER_SCAN_I18N + source[end:]


APP_KO_I18N = """  ko: {
    access_required: '접근 권한 필요',
    access_help: '운영자가 설정한 배포 접근 토큰을 입력하세요.',
    access_token: '접근 토큰',
    open_dashboard: '대시보드 열기',
    dashboard_title: '종목 선정 워크스페이스',
    data_not_loaded: '데이터 기준: 불러오지 않음',
    provider_not_loaded: '데이터 제공자: 불러오지 않음',
    ops_checking: '운영 상태: 확인 중',
    add_tickers: '종목 추가',
    add: '추가',
    run_scan: '스캔 실행',
    select_final: '최종 3개 선정',
    refresh: '새로고침',
    watchlist: '관심 종목',
    operations: '운영 상태',
    decision_first: '의사결정 우선 대시보드',
    entry_candidates: '진입 후보',
    final_selection: '최종 선정',
    run_selection_empty: '최종 후보를 보려면 선정을 실행하세요.',
    actionable_setups: '진입 검토 후보',
    ticker: '종목',
    archetype: '유형',
    score: '점수',
    status: '상태',
    allocation: '배분',
    data: '데이터',
    reason: '이유',
    run_scan_empty: '스캔을 실행하면 후보가 표시됩니다.',
    monitor_excluded: '관찰 또는 제외',
    lower_confidence_empty: '스캔 후 신뢰도가 낮은 종목이 여기에 표시됩니다.',
    legal_notice: '의사결정 보조용입니다. 자동 매매를 실행하지 않습니다.',
    risk_disclosure: '위험 고지',
    privacy: '개인정보',
    terms: '약관',
    ready: '준비됨',
    running: '실행 중',
    not_run: '미실행',
    failures: '실패',
    selection_completed: '선정이 {ms} ms 안에 완료되었습니다.',
    no_eligible: '조건을 충족하는 후보가 없습니다. 관심 종목 품질을 확인하거나 데이터 갱신 후 다시 실행하세요.',
    allocation_guide: '배분 가이드',
    no_excluded: '제외된 종목이 없습니다.',
    no_actionable: '진입 검토 후보가 없습니다.',
    provider: '데이터 제공자',
    data_as_of: '데이터 기준',
    ops_success: '운영 상태: 정상',
    ops_provider_issues: '운영 상태: 제공자 이슈 {count}건'
  }"""


APP_RENDER_SCAN_I18N = """  document.getElementById('actionable-meta').textContent = state.lang === 'ko'
    ? `${items.length}개 중 ${actionable.length}개 진입 검토 / ${elapsedMs} ms`
    : `${actionable.length} actionable / ${items.length} in ${elapsedMs} ms`;
  document.getElementById('excluded-meta').textContent = state.lang === 'ko'
    ? `${excluded.length}개 관찰`
    : `${excluded.length} monitor only`;
"""


DETAIL_KO_I18N = """  ko: {
    ticker_analysis: '종목 분석',
    dashboard: '대시보드',
    five_year_chart: '최근 5년 가격과 거래량',
    current_status: '현재 상태',
    ai_summary: 'AI 요약',
    industry_profile: '업종 및 종목 정보',
    selection_reason: '종목 선정 이유',
    expert_consensus: '전문가 합의 분석',
    required_review: '필수 검토 항목',
    score: '점수',
    review_state: '검토 상태',
    allocation_guide: '배분 가이드',
    risk_reference: '위험 기준',
    return_12w: '12주 수익률',
    return_12m: '12개월 수익률',
    drawdown_52w: '52주 낙폭',
    trend_score: '추세 점수',
    surge_score: '급등 점수',
    rs_vs_spy: 'SPY 대비 상대강도',
    intraday: '장중 시세',
    short_interest: '공매도 비율',
    options_pcr: '옵션 풋/콜 비율',
    analyst_score: '애널리스트 점수',
    data_coverage: '데이터 커버리지',
    coverage_state: '커버리지 상태',
    sector: '섹터',
    industry: '업종',
    company: '기업명',
    data_note: '데이터 안내',
    daily_points: '일봉 {count}개 / {freshness}',
    no_chart: '차트 데이터가 없습니다.',
    close_range: '종가 범위 {min} - {max}',
    why_selected: '선정 이유',
    signals: '긍정 신호',
    risks: '위험 요인',
    to: '~'
  }"""


LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Access</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="login-shell">
    <section class="login-panel" aria-label="Access required">
        <p class="eyebrow">VCB-Alt Screening Desk</p>
        <h1 data-i18n="access_required">Access required</h1>
        <p class="muted" data-i18n="access_help">Enter the deployment access token configured by the operator.</p>
        <form method="get" action="/">
        <label for="token" data-i18n="access_token">Access token</label>
        <input id="token" name="token" type="password" autocomplete="current-password" required>
        <button type="submit" data-i18n="open_dashboard">Open dashboard</button>
      </form>
    </section>
  </main>
</body>
</html>
"""


# The dashboard intentionally keeps the user-supplied dark operations-desk direction,
# but all candidate values come from the API so public beta users never see static demo scores.
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Market Discovery</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="app-shell">
    <header class="topbar" aria-label="Application header">
      <div>
        <p class="eyebrow">VCB-Alt Market Discovery</p>
        <h1 data-i18n="dashboard_title">Market-wide stock discovery</h1>
      </div>
      <div class="status-strip">
        <span id="provider">provider</span>
        <span id="runtime">ready</span>
        <div class="language-toggle" aria-label="Language">
          <button type="button" class="secondary lang-button" data-lang-option="en">EN</button>
          <button type="button" class="secondary lang-button" data-lang-option="ko">KR</button>
        </div>
      </div>
    </header>

    <section class="metadata-bar" aria-label="Data status">
      <span id="data-as-of" data-i18n="data_not_loaded">Data as of: not loaded</span>
      <span id="data-source" data-i18n="provider_not_loaded">Provider: not loaded</span>
      <span id="ops-state" class="status-dot good" data-i18n="ops_checking">Operational status: checking</span>
    </section>

    <section class="toolbar" aria-label="Screening actions">
      <form id="add-form" class="ticker-form">
        <label for="ticker-input" data-i18n="add_tickers">Manual watchlist</label>
        <input id="ticker-input" name="tickers" autocomplete="off" placeholder="PLTR MSTR VST">
        <button type="submit" data-i18n="add">Add</button>
      </form>
      <button id="scan-button" type="button" data-i18n="run_scan">Scan market</button>
      <button id="select-button" type="button" data-i18n="select_final">Select final 3</button>
      <button id="refresh-button" type="button" data-i18n="refresh">Refresh</button>
    </section>

    <section id="notice" class="notice" hidden></section>

    <div class="workspace">
      <aside class="sidebar" aria-label="Watchlist and operations">
        <section class="panel watchlist-panel">
          <div class="panel-head">
          <h2 data-i18n="watchlist">Manual watchlist</h2>
          <span id="watchlist-count">0</span>
          </div>
          <div id="watchlist" class="watchlist"></div>
        </section>

        <section class="panel ops-panel">
          <div class="panel-head">
            <h2 data-i18n="operations">Operations</h2>
            <span id="failure-count">0 failures</span>
          </div>
          <div id="readiness" class="readiness"></div>
          <div id="failures" class="ops-list"></div>
        </section>
      </aside>

      <section class="decision-area">
        <div class="section-head">
          <div>
            <p class="eyebrow" data-i18n="decision_first">Decision-first dashboard</p>
            <h2><span data-i18n="entry_candidates">Entry candidates</span> <span data-i18n="final_selection">Final selection</span></h2>
          </div>
          <span id="selection-meta" class="pill">Not run</span>
        </div>

        <section id="selection" class="candidate-grid" aria-label="Final selection">
          <div class="empty-state" data-i18n="run_selection_empty">Run selection to see final candidates.</div>
        </section>

        <section class="panel scan-panel">
          <div class="panel-head">
            <h2 data-i18n="actionable_setups">Actionable setups</h2>
            <span id="actionable-meta">Not run</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th data-i18n="ticker">Ticker</th>
                  <th data-i18n="archetype">Archetype</th>
                  <th data-i18n="score">Score</th>
                  <th data-i18n="status">Status</th>
                  <th data-i18n="allocation">Allocation</th>
                  <th data-i18n="data">Data</th>
                </tr>
              </thead>
              <tbody id="actionable-body">
                <tr><td colspan="6" class="empty-state" data-i18n="run_scan_empty">Run scan to populate candidates.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel scan-panel muted-panel">
          <div class="panel-head">
            <h2 data-i18n="monitor_excluded">Monitor or excluded</h2>
            <span id="excluded-meta">Not run</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th data-i18n="ticker">Ticker</th>
                  <th data-i18n="archetype">Archetype</th>
                  <th data-i18n="score">Score</th>
                  <th data-i18n="status">Status</th>
                  <th data-i18n="reason">Reason</th>
                  <th data-i18n="data">Data</th>
                </tr>
              </thead>
              <tbody id="excluded-body">
                <tr>
                  <td colspan="6" class="empty-state" data-i18n="lower_confidence_empty">
                    Lower-confidence names appear here after scanning.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </div>
    <footer class="legal-footer" aria-label="Legal and disclosure links">
      <span data-i18n="legal_notice">Decision support only. No automatic trading.</span>
      <a href="/risk-disclosure" data-i18n="risk_disclosure">Risk disclosure</a>
      <a href="/privacy" data-i18n="privacy">Privacy</a>
      <a href="/terms" data-i18n="terms">Terms</a>
    </footer>
  </main>
  <div id="detail-modal" class="modal" hidden>
    <section class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="detail-title">
      <button id="detail-close" class="icon-button" type="button" aria-label="Close detail">x</button>
      <div id="detail-content"></div>
    </section>
  </div>
  <script src="/assets/app.js"></script>
</body>
</html>
"""


DETAIL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Ticker Analysis</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="app-shell detail-shell">
    <header class="topbar" aria-label="Ticker analysis header">
      <div>
        <p class="eyebrow" data-i18n="ticker_analysis">Ticker analysis</p>
        <h1 id="detail-symbol">Loading...</h1>
      </div>
      <div class="status-strip">
        <span id="detail-provider">provider</span>
        <a class="pill" href="/" data-i18n="dashboard">Dashboard</a>
        <div class="language-toggle" aria-label="Language">
          <button type="button" class="secondary lang-button" data-lang-option="en">EN</button>
          <button type="button" class="secondary lang-button" data-lang-option="ko">KR</button>
        </div>
      </div>
    </header>

    <section id="detail-notice" class="notice" hidden></section>

    <section class="detail-layout" aria-label="Ticker status analysis">
      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="five_year_chart">Five-year price and volume</h2>
          <span id="chart-meta">Loading</span>
        </div>
        <div class="chart-wrap">
          <svg id="price-chart" role="img" aria-label="Five-year chart"></svg>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="current_status">Current status</h2>
          <span id="review-state">Loading</span>
        </div>
        <div id="status-grid" class="detail-grid"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="ai_summary">AI summary</h2>
          <span id="ai-provider">Loading</span>
        </div>
        <div id="ai-summary-body" class="analysis-block"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="industry_profile">Industry and profile</h2>
          <span id="profile-source">Loading</span>
        </div>
        <div id="profile-body" class="analysis-block"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="selection_reason">Selection reason</h2>
          <span id="score-version">Loading</span>
        </div>
        <div id="rationale-body" class="analysis-block"></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 data-i18n="expert_consensus">Expert consensus</h2>
          <span data-i18n="required_review">Required review set</span>
        </div>
        <div id="consensus-body" class="analysis-block"></div>
      </section>
    </section>
  </main>
  <script src="/assets/detail.js"></script>
</body>
</html>
"""


TERMS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Terms</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="doc-shell">
    <p class="eyebrow">VCB-Alt Screening Desk</p>
    <h1>Terms Of Use</h1>
    <p>This starter document is an operational placeholder and must be reviewed by qualified counsel before broad public launch.</p>
    <h2>Decision Support Only</h2>
    <p>
      VCB-Alt provides screening workflow output for user review.
      It does not provide personalized investment advice, execute trades, manage assets, or guarantee outcomes.
    </p>
    <h2>User Responsibility</h2>
    <p>Users are responsible for verifying data, assessing suitability, and making their own final decisions.</p>
    <h2>Service Limits</h2>
    <p>The current deployment is a token-protected beta. Availability, data freshness, and provider access may vary.</p>
    <p><a href="/">Back to dashboard</a></p>
  </main>
</body>
</html>
"""


PRIVACY_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Privacy</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="doc-shell">
    <p class="eyebrow">VCB-Alt Screening Desk</p>
    <h1>Privacy Notice</h1>
    <p>This starter notice is an operational placeholder and must be legally reviewed before broad public launch.</p>
    <h2>Current Data</h2>
    <p>
      The beta stores watchlist tickers, evaluation outputs, operation logs, and failed-job records.
      It does not require brokerage credentials.
    </p>
    <h2>Secrets</h2>
    <p>Access tokens and provider credentials must be configured as environment variables and must not be logged or committed.</p>
    <h2>Future SaaS Requirement</h2>
    <p>Public signup requires per-user accounts, export/delete workflows, retention policy, and tenant isolation before launch.</p>
    <p><a href="/">Back to dashboard</a></p>
  </main>
</body>
</html>
"""


RISK_DISCLOSURE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Risk Disclosure</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <main class="doc-shell">
    <p class="eyebrow">VCB-Alt Screening Desk</p>
    <h1>Risk Disclosure</h1>
    <p>This starter disclosure is not legal advice and must be reviewed before public launch.</p>
    <h2>Market Risk</h2>
    <p>Stocks can lose value quickly. High-volatility archetypes can move sharply and may be unsuitable for many users.</p>
    <h2>Data Risk</h2>
    <p>
      Market-data providers may be delayed, incomplete, stale, or unavailable.
      Price/volume-only providers do not supply fundamentals, news, short interest, or options data.
    </p>
    <h2>Model Risk</h2>
    <p>Scores are heuristic research signals. They can be wrong, incomplete, or misinterpreted.</p>
    <p><a href="/">Back to dashboard</a></p>
  </main>
</body>
</html>
"""


APP_CSS = """
:root {
  color-scheme: dark;
  --bg: #101312;
  --ink: #e6e8e6;
  --muted: #a4ada9;
  --line: #2b3430;
  --panel: #171b19;
  --panel-soft: #1f2522;
  --panel-deep: #0c0f0e;
  --accent: #82d6b4;
  --accent-ink: #ffffff;
  --warn: #f2bd66;
  --bad: #ff8a80;
  --good: #57d68d;
  --shadow: rgba(0, 0, 0, 0.22);
}
* { box-sizing: border-box; }
/* Responsive guards: every card, table cell, and metric box must wrap content instead of escaping its container. */
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, "Noto Sans KR", "Apple SD Gothic Neo", Arial, sans-serif;
  background: var(--bg);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
body, button, input, table { font: inherit; }
body, p, h1, h2, h3, span, a, button, input, td, th, li, strong {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: keep-all;
}
.app-shell { min-height: 100vh; display: flex; flex-direction: column; }
.login-shell { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
.login-panel { width: min(420px, 100%); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 22px; }
.login-panel form { display: grid; gap: 10px; margin-top: 18px; }
.doc-shell { width: min(760px, 100%); margin: 0 auto; padding: 36px 22px; }
.doc-shell h1 { margin-bottom: 18px; }
.doc-shell h2 { margin-top: 28px; }
.doc-shell a, .legal-footer a { color: var(--accent); }
.topbar {
  min-height: 82px;
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--panel-deep);
  min-width: 0;
}
.eyebrow { margin: 0 0 4px; color: var(--accent); font-size: 12px; font-weight: 700; text-transform: uppercase; }
h1, h2 { margin: 0; letter-spacing: 0; }
h1 { font-size: 26px; line-height: 1.15; }
h2 { font-size: 16px; }
.status-strip { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; align-items: center; min-width: 0; }
.status-strip span, .panel-head span, .pill {
  border: 1px solid var(--line);
  background: var(--panel-soft);
  border-radius: 8px;
  padding: 5px 9px;
  color: var(--muted);
  font-size: 12px;
  max-width: 100%;
}
.language-toggle { display: inline-flex; gap: 4px; flex-wrap: nowrap; align-items: center; }
.lang-button {
  width: 38px;
  min-width: 38px;
  height: 30px;
  padding: 0;
  font-size: 12px;
  color: var(--muted);
}
.lang-button.active {
  background: var(--accent);
  color: #06100c;
  border-color: var(--accent);
}
.metadata-bar {
  min-height: 38px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  padding: 9px 24px;
  border-bottom: 1px solid var(--line);
  background: #121615;
  color: var(--muted);
  font-size: 12px;
}
.status-dot::before {
  content: "";
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 99px;
  margin-right: 6px;
  background: var(--good);
}
.status-dot.warn::before { background: var(--warn); }
.status-dot.bad::before { background: var(--bad); }
.toolbar {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) repeat(3, max-content);
  gap: 10px;
  align-items: end;
  padding: 14px 24px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}
.ticker-form { display: grid; grid-template-columns: 90px 1fr max-content; gap: 8px; align-items: center; }
label { color: var(--muted); font-size: 13px; }
input {
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0 10px;
  font-size: 14px;
  background: var(--panel-soft);
  color: var(--ink);
}
button {
  height: 38px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #06100c;
  border-radius: 6px;
  padding: 0 13px;
  font-weight: 700;
  cursor: pointer;
  white-space: normal;
  line-height: 1.15;
}
button.secondary { background: var(--panel-soft); color: var(--ink); border-color: var(--line); }
button:disabled { opacity: 0.55; cursor: wait; }
.notice {
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  background: var(--panel);
  padding: 10px 12px;
  margin: 12px 24px 0;
  border-radius: 6px;
}
.notice.error { border-left-color: var(--bad); }
.workspace {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(260px, 310px) minmax(0, 1fr);
  min-height: 0;
  min-width: 0;
}
.legal-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  padding: 14px 24px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  background: var(--panel-deep);
  font-size: 12px;
}
.detail-shell { min-height: 100vh; }
.detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 18px;
  padding: 18px 20px 36px;
  min-width: 0;
}
.detail-layout .panel:first-child { grid-row: span 2; }
.chart-wrap { min-height: 360px; padding: 14px; overflow: hidden; }
#price-chart { width: 100%; height: auto; min-height: 320px; aspect-ratio: 15 / 7; display: block; }
.analysis-block { padding: 14px; color: var(--ink); font-size: 14px; line-height: 1.55; }
.analysis-block p { margin: 0 0 10px; }
.analysis-block ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
.analysis-block li::before { content: ">"; color: var(--accent); margin-right: 7px; }
.sidebar {
  border-right: 1px solid var(--line);
  background: #121615;
  display: grid;
  grid-template-rows: minmax(280px, 1fr) minmax(180px, 0.45fr);
  min-height: 0;
}
.decision-area {
  min-width: 0;
  overflow-y: auto;
  padding: 18px 20px 36px;
  display: grid;
  gap: 20px;
}
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: end;
}
.section-head h2 {
  font-size: 28px;
  line-height: 1.15;
}
.section-head h2 span {
  color: var(--muted);
  font-size: 16px;
  font-weight: 400;
  margin-left: 8px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  min-width: 0;
  max-width: 100%;
  box-shadow: 0 8px 24px var(--shadow);
  overflow: hidden;
}
.sidebar .panel { border-width: 0 0 1px 0; border-radius: 0; box-shadow: none; overflow: hidden; min-height: 0; }
.muted-panel { opacity: 0.86; }
.panel-head {
  min-height: 48px;
  border-bottom: 1px solid var(--line);
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  min-width: 0;
}
.watchlist, .selection-list, .ops-list, .readiness { padding: 12px 14px; }
.watchlist { overflow-y: auto; max-height: calc(100vh - 260px); }
.ticker-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--line);
  padding: 9px 0;
}
.ticker-row:last-child { border-bottom: 0; }
.ticker-row button { height: 28px; padding: 0 8px; background: transparent; color: var(--bad); border-color: var(--line); }
.candidate-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.candidate-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  display: grid;
  gap: 12px;
  min-height: 250px;
  box-shadow: 0 8px 24px var(--shadow);
  min-width: 0;
}
.candidate-card:hover, tr.clickable:hover { border-color: rgba(130, 214, 180, 0.55); }
.candidate-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}
.ticker-lockup {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.rank {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  background: rgba(130, 214, 180, 0.12);
  color: var(--accent);
  border: 1px solid rgba(130, 214, 180, 0.35);
  border-radius: 6px;
  font-weight: 800;
}
.ticker-symbol { font-size: 28px; font-weight: 800; letter-spacing: 0; max-width: 100%; }
.score { font-weight: 800; text-align: right; font-size: 28px; color: var(--good); }
.score small { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; font-weight: 700; }
.candidate-meta {
  color: var(--muted);
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
  font-size: 13px;
}
.reason-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.reason-list li {
  color: var(--ink);
  font-size: 13px;
  line-height: 1.45;
}
.reason-list li::before {
  content: ">";
  color: var(--accent);
  margin-right: 7px;
}
.candidate-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
  flex-wrap: wrap;
}
.muted { color: var(--muted); }
.empty-state { color: var(--muted); padding: 18px 0; }
.table-wrap { overflow-x: auto; max-width: 100%; }
table { width: 100%; border-collapse: collapse; min-width: 720px; table-layout: fixed; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); font-size: 13px; }
th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
.badge {
  display: inline-block;
  border-radius: 8px;
  padding: 4px 8px;
  background: var(--panel-soft);
  color: var(--muted);
  border: 1px solid var(--line);
}
.badge.good { background: rgba(87, 214, 141, 0.12); color: var(--good); border-color: rgba(87, 214, 141, 0.28); }
.badge.warn { background: rgba(242, 189, 102, 0.12); color: var(--warn); border-color: rgba(242, 189, 102, 0.28); }
.badge.bad { background: rgba(255, 138, 128, 0.10); color: var(--bad); border-color: rgba(255, 138, 128, 0.25); }
.readiness { border-bottom: 1px solid var(--line); font-size: 13px; color: var(--muted); }
.ops-list { font-size: 13px; color: var(--muted); }
.clickable { cursor: pointer; }
.modal {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.62);
}
.modal[hidden] { display: none; }
.modal-panel {
  width: min(760px, 100%);
  max-height: min(760px, calc(100vh - 40px));
  overflow-y: auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 20px;
  position: relative;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
}
.icon-button {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 34px;
  padding: 0;
  background: var(--panel-soft);
  color: var(--ink);
  border-color: var(--line);
}
.detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0; padding: 0 14px 14px; }
.metric-box { border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: var(--panel-deep); }
.metric-box span { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; margin-bottom: 4px; }
.metric-box strong { display: block; font-size: 18px; line-height: 1.2; }
@media (max-width: 900px) {
  .topbar, .toolbar, .ticker-form, .workspace, .section-head { display: block; }
  .topbar, .metadata-bar, .toolbar, .decision-area, .detail-layout, .legal-footer { padding-left: 14px; padding-right: 14px; }
  .status-strip { justify-content: flex-start; margin-top: 12px; }
  .toolbar > *, .ticker-form > * { width: 100%; margin-bottom: 8px; }
  .sidebar { display: block; border-right: 0; }
  .watchlist { max-height: none; }
  .candidate-grid { grid-template-columns: 1fr; }
  .metadata-bar { display: grid; }
  .detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .detail-layout { display: grid; grid-template-columns: 1fr; padding: 14px; }
  .chart-wrap { min-height: 260px; padding: 10px; }
  #price-chart { min-height: 240px; }
  .candidate-top { flex-wrap: wrap; }
  .score { text-align: left; }
  table { min-width: 0; table-layout: auto; }
  thead { display: none; }
  tbody, tr, td { display: block; width: 100%; }
  tr {
    border-bottom: 1px solid var(--line);
    padding: 8px 0;
  }
  td {
    border-bottom: 0;
    display: grid;
    grid-template-columns: minmax(92px, 34%) minmax(0, 1fr);
    gap: 10px;
    padding: 7px 12px;
  }
  td::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 700;
  }
  td.empty-state {
    display: block;
  }
  td.empty-state::before { content: ""; display: none; }
}
@media (max-width: 520px) {
  h1 { font-size: 22px; }
  .section-head h2 { font-size: 22px; }
  .ticker-symbol, .score { font-size: 24px; }
  .detail-grid { grid-template-columns: 1fr; }
  .panel-head { align-items: flex-start; flex-direction: column; }
  td { grid-template-columns: 1fr; }
  .language-toggle { width: 100%; }
  .lang-button { flex: 1; }
}
"""


APP_JS = """
const state = {
  scan: [],
  selection: null,
  failures: [],
  config: null,
  providerStatus: null,
  sessionToken: localStorage.getItem('vcb_session_token') || '',
  sessionUser: null,
  lang: localStorage.getItem('vcb_lang') || 'en'
};

const I18N = {
  en: {
    access_required: 'Access required',
    access_help: 'Enter the deployment access token configured by the operator.',
    access_token: 'Access token',
    open_dashboard: 'Open dashboard',
    dashboard_title: 'Market-wide stock discovery',
    data_not_loaded: 'Data as of: not loaded',
    provider_not_loaded: 'Provider: not loaded',
    ops_checking: 'Operational status: checking',
    add_tickers: 'Manual watchlist',
    add: 'Add',
    run_scan: 'Scan market',
    select_final: 'Select final 3',
    refresh: 'Refresh',
    watchlist: 'Manual watchlist',
    operations: 'Operations',
    decision_first: 'Decision-first dashboard',
    entry_candidates: 'Entry candidates',
    final_selection: 'Final selection',
    run_selection_empty: 'Run selection to see final candidates.',
    actionable_setups: 'Actionable setups',
    ticker: 'Ticker',
    archetype: 'Archetype',
    score: 'Score',
    status: 'Status',
    allocation: 'Allocation',
    data: 'Data',
    reason: 'Reason',
    run_scan_empty: 'Scan the market to populate candidates.',
    monitor_excluded: 'Monitor or excluded',
    lower_confidence_empty: 'Lower-confidence market names appear here after scanning.',
    legal_notice: 'Decision support only. No automatic trading.',
    risk_disclosure: 'Risk disclosure',
    privacy: 'Privacy',
    terms: 'Terms',
    ready: 'ready',
    running: 'running',
    not_run: 'Not run',
    failures: 'failures',
    selection_completed: 'Selection completed in {ms} ms.',
    no_eligible: 'No eligible candidates. Check live data coverage or run again after data refresh.',
    allocation_guide: 'Allocation guide',
    no_excluded: 'No excluded names.',
    no_actionable: 'No actionable setups.',
    provider: 'Provider',
    data_as_of: 'Data as of',
    ops_success: 'Operational status: success',
    ops_provider_issues: 'Operational status: {count} provider issue(s)'
  },
  ko: {
    access_required: '접근 권한 필요',
    access_help: '운영자가 설정한 배포 접근 토큰을 입력하세요.',
    access_token: '접근 토큰',
    open_dashboard: '대시보드 열기',
    dashboard_title: '종목 선정 워크스페이스',
    data_not_loaded: '데이터 기준: 불러오지 않음',
    provider_not_loaded: '데이터 제공자: 불러오지 않음',
    ops_checking: '운영 상태: 확인 중',
    add_tickers: '종목 추가',
    add: '추가',
    run_scan: '스캔 실행',
    select_final: '최종 3개 선정',
    refresh: '새로고침',
    watchlist: '관심 종목',
    operations: '운영 상태',
    decision_first: '의사결정 우선 대시보드',
    entry_candidates: '진입 후보',
    final_selection: '최종 선정',
    run_selection_empty: '최종 후보를 보려면 선정을 실행하세요.',
    actionable_setups: '진입 검토 후보',
    ticker: '종목',
    archetype: '유형',
    score: '점수',
    status: '상태',
    allocation: '배분',
    data: '데이터',
    reason: '이유',
    run_scan_empty: '스캔을 실행하면 후보가 표시됩니다.',
    monitor_excluded: '관찰 또는 제외',
    lower_confidence_empty: '스캔 후 신뢰도가 낮은 종목이 여기에 표시됩니다.',
    legal_notice: '의사결정 보조용입니다. 자동 매매를 실행하지 않습니다.',
    risk_disclosure: '위험 고지',
    privacy: '개인정보',
    terms: '약관',
    ready: '준비됨',
    running: '실행 중',
    not_run: '미실행',
    failures: '실패',
    selection_completed: '선정이 {ms} ms 안에 완료되었습니다.',
    no_eligible: '조건을 충족하는 후보가 없습니다. 관심 종목 품질을 확인하거나 데이터 갱신 후 다시 실행하세요.',
    allocation_guide: '배분 가이드',
    no_excluded: '제외된 종목이 없습니다.',
    no_actionable: '진입 검토 후보가 없습니다.',
    provider: '데이터 제공자',
    data_as_of: '데이터 기준',
    ops_success: '운영 상태: 정상',
    ops_provider_issues: '운영 상태: 제공자 이슈 {count}건'
  }
};

function t(key, values = {}) {
  const text = (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;
  return Object.entries(values).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, value), text);
}

function applyTranslations() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.langOption === state.lang);
    button.setAttribute('aria-pressed', String(button.dataset.langOption === state.lang));
  });
  document.getElementById('runtime').textContent = t('ready');
}

function setLanguage(lang) {
  state.lang = lang === 'ko' ? 'ko' : 'en';
  localStorage.setItem('vcb_lang', state.lang);
  applyTranslations();
  if (state.selection) renderSelection(state.selection, state.selection.elapsed_ms || 0);
  if (state.scan.length) renderScan(state.scan);
  updateDataStatus([...(state.scan || []), ...((state.selection && state.selection.selected) || [])], state.failures || []);
}

function initLanguageToggle() {
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => setLanguage(button.dataset.langOption));
  });
  applyTranslations();
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.sessionToken) headers.Authorization = `Bearer ${state.sessionToken}`;
  const response = await fetch(path, {
    ...options,
    headers
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error?.message || payload.message || 'Request failed');
  return payload.data;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const KO_DYNAMIC = {
  archetypes: {
    A_AI_TECH: 'AI/테크 메가트렌드',
    B_CRYPTO_PIVOT: '크립토 전환',
    C_QUANTUM: '퀀텀/신흥 기술',
    D_BIOTECH: '바이오 촉매',
    E_SHORT_SQUEEZE: '숏스퀴즈',
    F_PICK_SHOVEL: 'AI 인프라 수혜',
    G_TECHNICAL_MOMENTUM: '기술적 모멘텀'
  },
  publicLabels: {
    'High-priority review candidate': '우선 검토 후보',
    'Review candidate': '검토 후보',
    'Monitor only': '관찰 대상',
    'Needs review': '검토 필요',
    'High-scoring watchlist candidate': '고득점 관심 후보',
    'Watchlist candidate': '관심 후보',
    'No current setup': '현재 조건 미충족'
  },
  coverageLabels: {
    'multi-source': '다중 데이터',
    enriched: '보강 데이터',
    'price-volume-only': '가격/거래량 한정',
    insufficient: '부족',
    unknown: '알 수 없음'
  },
  sources: {
    sample: '샘플',
    'sample-placeholder': '샘플 대체값',
    yahoo: '야후',
    yahoo_chart: '야후 차트',
    stooq: '스투크',
    manual: '수동 CSV',
    finnhub: '핀허브',
    alpaca: '알파카',
    'alpaca-intraday': '알파카 장중',
    template: '템플릿',
    openai: 'OpenAI',
    local: '로컬'
  },
  modes: {
    offline: '오프라인',
    operator_csv: '운영자 CSV',
    eod_market_data: '일봉 시장 데이터',
    unknown: '알 수 없음'
  },
  dataQuality: {
    offline: '오프라인',
    'eod-market': '일봉 시장 데이터',
    'partial-eod-market': '부분 일봉 시장 데이터',
    'thin-eod-market': '부족한 일봉 시장 데이터',
    'stale-eod-market': '오래된 일봉 시장 데이터'
  },
  rejectionReasons: {
    'Score below entry threshold.': '점수가 진입 검토 기준보다 낮습니다.',
    'Monitor only.': '관찰 대상으로 유지합니다.',
    'Portfolio slot limit reached.': '최대 편입 종목 수에 도달했습니다.',
    'Duplicate primary archetype avoided.': '같은 주요 유형의 중복 편입을 피했습니다.',
    'High-volatility archetype limit reached.': '고변동성 유형 제한에 도달했습니다.',
    'Total suggested exposure limit reached.': '총 권장 비중 한도에 도달했습니다.'
  }
};

function isKo() {
  return state.lang === 'ko';
}

function translateSource(value) {
  if (!isKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function translateMode(value) {
  if (!isKo()) return value || 'unknown';
  return KO_DYNAMIC.modes[value] || value || KO_DYNAMIC.modes.unknown;
}

function translateDataQuality(value) {
  if (!isKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => KO_DYNAMIC.dataQuality[part] || KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function archetypeLabel(item) {
  if (!isKo()) return item.primary_archetype_label;
  return KO_DYNAMIC.archetypes[item.primary_archetype] || item.primary_archetype_label;
}

function publicLabel(item) {
  const label = item.public_label || item.decision_label || item.status || 'Needs review';
  return isKo() ? KO_DYNAMIC.publicLabels[label] || label : label;
}

function coverageLabel(value) {
  return isKo() ? KO_DYNAMIC.coverageLabels[value] || value || '-' : value || '-';
}

function translateMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function translateText(value, item = {}) {
  const text = String(value || '');
  if (!isKo() || !text) return text;

  let match = text.match(/^Primary archetype is (.+) with base score ([-0-9.]+)\.$/);
  if (match) return `주요 유형은 ${archetypeLabel(item)}이며 기본 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Complexity modifier is ([-0-9.]+); combined score is ([-0-9.]+)\.$/);
  if (match) return `복합 보정값은 ${match[1]}점이며 최종 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Data quality: (.+)\.$/);
  if (match) return `데이터 품질: ${translateDataQuality(match[1])}.`;
  match = text.match(/^Trend template score: ([-0-9.]+)\/100\.$/);
  if (match) return `추세 템플릿 점수: 100점 만점에 ${match[1]}점.`;
  match = text.match(/^Surge score: ([-0-9.]+)\/100\.$/);
  if (match) return `급등 점수: 100점 만점에 ${match[1]}점.`;
  match = text.match(/^Data coverage: ([-0-9.]+)\/100 \(([^)]+)\)\. (.+)$/);
  if (match) return `데이터 커버리지: 100점 만점에 ${match[1]}점(${coverageLabel(match[2])}). ${translateText(match[3], item)}`;
  match = text.match(/^Missing: (.+)\.$/);
  if (match) return `누락 데이터: ${translateMissingList(match[1])}.`;
  match = text.match(/^Research enrichment applied from (.+) as of (.+)\.$/);
  if (match) return `리서치 보강 데이터가 ${translateSource(match[1])}에서 적용되었습니다. 기준일: ${match[2]}.`;
  match = text.match(/^Intraday quote layer: (.+) price (.+) as of (.+)\.$/);
  if (match) return `장중 시세 계층: ${translateSource(match[1])} 가격 ${match[2]}, 기준 시각 ${match[3]}.`;
  match = text.match(/^(.+) score is ([-0-9.]+)\.$/);
  if (match) return `${archetypeLabel(item)} 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Allocation guide is ([-0-9.]+)%\.$/);
  if (match) return `권장 검토 비중은 ${match[1]}%입니다.`;

  const exact = {
    'Score is above the MVP portfolio-manager threshold of 55.': '점수가 MVP 포트폴리오 관리 기준인 55점을 넘었습니다.',
    'Score passed the numeric threshold, but final selection is blocked until enrichment data is present.':
      '점수 기준은 통과했지만 보강 데이터가 없어서 최종 선정은 보류됩니다.',
    'Score is below the MVP portfolio-manager threshold of 55; wait.': '점수가 MVP 포트폴리오 관리 기준인 55점보다 낮아 대기합니다.',
    'Decision support only; not investment advice.': '의사결정 보조 정보일 뿐 투자 자문이 아닙니다.',
    'No automatic trading is performed.': '자동 매매는 실행하지 않습니다.',
    'Result uses sample/offline data, not live market data.': '이 결과는 실시간 시장 데이터가 아니라 샘플/오프라인 데이터를 사용합니다.',
    'High-volatility archetype: avoid stacking multiple simultaneous positions.':
      '고변동성 유형입니다. 같은 시점에 여러 고변동성 포지션을 겹치지 않도록 검토하세요.',
    ['Market-data provider supplies EOD price/volume only; '
      + 'fundamentals and catalysts remain unavailable unless research data is configured.']:
      '시장 데이터 제공자는 일봉 가격/거래량만 제공합니다. 리서치 데이터가 설정되지 않으면 재무와 촉매 데이터는 비어 있습니다.',
    'Required market, fundamental, catalyst, and positioning groups present.': '시장, 재무, 촉매, 포지셔닝 데이터 그룹이 모두 존재합니다.',
    'Entry threshold is met.': '진입 검토 기준을 충족했습니다.',
    'Entry threshold is not met.': '진입 검토 기준을 충족하지 못했습니다.',
    'Current provider supplies end-of-day/delayed chart data, not tick-by-tick real-time data.':
      '현재 제공자는 틱 단위 실시간 데이터가 아니라 일봉/지연 차트 데이터를 제공합니다.',
    ...KO_DYNAMIC.rejectionReasons
  };
  return exact[text] || text;
}

function translateReadinessDecision(value) {
  if (!isKo()) return value || '';
  const labels = {
    READY_FOR_PRIVATE_BETA: '비공개 베타 가능',
    READY_FOR_PUBLIC_BETA: '공개 베타 가능',
    NOT_READY: '출시 불가',
    NOT_READY_FOR_1000_USER_SAAS: '1000명 SaaS 공개 전 보완 필요'
  };
  return labels[value] || value || '';
}

function showNotice(message, error = false) {
  const box = document.getElementById('notice');
  box.hidden = false;
  box.className = `notice${error ? ' error' : ''}`;
  box.textContent = message;
}

function setBusy(busy) {
  document.querySelectorAll('button').forEach((button) => { button.disabled = busy; });
  document.getElementById('runtime').textContent = busy ? t('running') : t('ready');
}

function endpoint(legacyPath, tenantPath) {
  return state.config && state.config.user_auth_enabled ? tenantPath : legacyPath;
}

function starterTickers() {
  return 'PLTR MSTR VST AAPL GME RGTI SMMT';
}

function randomId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replaceAll('-', '');
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
}

function storeGeneratedCredentials() {
  const id = randomId();
  const email = `browser-${id}@example.invalid`;
  const password = `Browser-${id}-password`;
  localStorage.setItem('vcb_user_email', email);
  localStorage.setItem('vcb_user_password', password);
  return { email, password };
}

async function ensureUserSession() {
  if (!state.config || !state.config.user_auth_enabled) return;
  if (state.sessionToken) {
    try {
      state.sessionUser = await api('/api/me');
      return;
    } catch (error) {
      localStorage.removeItem('vcb_session_token');
      state.sessionToken = '';
    }
  }
  let email = localStorage.getItem('vcb_user_email');
  let password = localStorage.getItem('vcb_user_password');
  if (!email || !password) {
    ({ email, password } = storeGeneratedCredentials());
  }
  // Public demo browsers get an isolated tenant automatically so the scan button never
  // falls back to blocked legacy global APIs when SaaS auth is enabled.
  try {
    const registered = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, tenant_name: 'Browser workspace' })
    });
    state.sessionToken = registered.session_token;
    state.sessionUser = registered.user;
  } catch (error) {
    try {
      const loggedIn = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      state.sessionToken = loggedIn.session_token;
      state.sessionUser = loggedIn.user;
    } catch (loginError) {
      ({ email, password } = storeGeneratedCredentials());
      const registered = await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, tenant_name: 'Browser workspace' })
      });
      state.sessionToken = registered.session_token;
      state.sessionUser = registered.user;
    }
  }
  localStorage.setItem('vcb_session_token', state.sessionToken);
}

async function ensureStarterWatchlist() {
  if (!state.config || !state.config.user_auth_enabled) return;
  const data = await api('/api/user/watchlist');
  if (!data.items.length) {
    await api('/api/user/watchlist', { method: 'POST', body: JSON.stringify({ tickers: starterTickers() }) });
  }
}

async function loadConfig() {
  const [config, providerStatus] = await Promise.all([
    api('/api/config'),
    api('/api/provider-status')
  ]);
  state.config = config;
  state.providerStatus = providerStatus;
  const mode = providerStatus.capabilities?.mode || 'unknown';
  document.getElementById('provider').textContent = isKo()
    ? `${translateSource(providerStatus.provider)} 데이터`
    : `${providerStatus.provider} data`;
  document.getElementById('data-source').textContent =
    `${t('provider')}: ${translateSource(providerStatus.provider)} / ${translateMode(mode)}`;
  document.getElementById('ops-state').textContent = config.external_api_enabled
    ? (state.lang === 'ko' ? '운영 상태: 외부 데이터 활성화' : 'Operational status: external data enabled')
    : (state.lang === 'ko' ? '운영 상태: 오프라인/샘플 모드' : 'Operational status: offline/sample mode');
}

async function loadWatchlist() {
  const data = await api(endpoint('/api/watchlist', '/api/user/watchlist'));
  document.getElementById('watchlist-count').textContent = state.lang === 'ko' ? `${data.count}개 종목` : `${data.count} tickers`;
  const target = document.getElementById('watchlist');
  if (!data.items.length) {
    target.innerHTML = `<div class="empty-state">${state.lang === 'ko' ? '시작하려면 종목을 추가하세요.' : 'Add tickers to begin.'}</div>`;
    return;
  }
  target.innerHTML = data.items.map((item) => `
    <div class="ticker-row">
      <strong>${escapeHtml(item.ticker)}</strong>
      <button type="button" data-remove="${escapeHtml(item.ticker)}">${state.lang === 'ko' ? '삭제' : 'Remove'}</button>
    </div>
  `).join('');
  target.querySelectorAll('[data-remove]').forEach((button) => {
    button.addEventListener('click', () => removeTicker(button.dataset.remove));
  });
}

async function loadOps() {
  const [readiness, failures] = await Promise.all([
    api('/api/saas-readiness'),
    api('/api/failures')
  ]);
  state.failures = failures.items || [];
  document.getElementById('failure-count').textContent = `${failures.count} ${t('failures')}`;
  const opsState = document.getElementById('ops-state');
  opsState.className = `status-dot ${failures.count ? 'warn' : 'good'}`;
  opsState.textContent = failures.count
    ? (state.lang === 'ko' ? '운영 상태: 실패 감지' : 'Operational status: failures detected')
    : t('ops_success');
  document.getElementById('readiness').innerHTML = `
    <strong>${escapeHtml(translateReadinessDecision(readiness.decision))}</strong><br>
    ${state.lang === 'ko'
      ? '프라이빗 베타 스크리닝은 가능합니다. 공개 SaaS 출시는 인증, 영구 저장소, 부하 테스트, 법률 검토가 더 필요합니다.'
      : 'Private-beta screening is available. Public SaaS launch still requires auth, persistence, load testing, and legal review.'}
  `;
  const target = document.getElementById('failures');
  target.innerHTML = failures.items.length
    ? failures.items.map((item) => `<div>${escapeHtml(item.created_at)}: ${escapeHtml(item.message)}</div>`).join('')
    : `<div>${state.lang === 'ko' ? '최근 실패가 없습니다.' : 'No recent failures.'}</div>`;
}

async function addTickers(event) {
  event.preventDefault();
  const input = document.getElementById('ticker-input');
  const tickers = input.value.trim();
  if (!tickers) return;
  setBusy(true);
  try {
    const data = await api(endpoint('/api/watchlist', '/api/user/watchlist'), { method: 'POST', body: JSON.stringify({ tickers }) });
    input.value = '';
    showNotice(state.lang === 'ko'
      ? `추가됨: ${data.added.join(', ') || '없음'}; 기존: ${data.existing.join(', ') || '없음'}`
      : `Added: ${data.added.join(', ') || 'none'}; existing: ${data.existing.join(', ') || 'none'}`);
    await loadWatchlist();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function removeTicker(ticker) {
  setBusy(true);
  try {
    await api(`${endpoint('/api/watchlist', '/api/user/watchlist')}?ticker=${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    showNotice(state.lang === 'ko' ? `${ticker} 삭제됨.` : `${ticker} removed.`);
    await loadWatchlist();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function runScan() {
  setBusy(true);
  try {
    const data = await api(endpoint('/api/scan', '/api/user/scan'), { method: state.config?.user_auth_enabled ? 'POST' : 'GET' });
    state.scan = data.items;
    renderScan(data.items, data.elapsed_ms);
    if (data.selection) {
      state.selection = data.selection;
      state.selection.elapsed_ms = data.elapsed_ms;
      renderSelection(data.selection, data.elapsed_ms);
    }
    updateDataStatus(data.items, data.failures || []);
    showNotice(state.lang === 'ko' ? `스캔이 ${data.elapsed_ms} ms 안에 완료되었습니다.` : `Scan completed in ${data.elapsed_ms} ms.`);
    await loadOps();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderScan(items, elapsedMs = 0) {
  const sorted = [...items].sort((a, b) => b.combined_score - a.combined_score);
  const actionable = sorted.filter((item) => item.can_enter);
  const excluded = sorted.filter((item) => !item.can_enter);
  document.getElementById('actionable-meta').textContent = state.lang === 'ko'
    ? `${items.length}개 중 ${actionable.length}개 진입 검토 / ${elapsedMs} ms`
    : `${actionable.length} actionable / ${items.length} in ${elapsedMs} ms`;
  document.getElementById('excluded-meta').textContent = state.lang === 'ko'
    ? `${excluded.length}개 관찰`
    : `${excluded.length} monitor only`;
  renderTable('actionable-body', actionable, false);
  renderTable('excluded-body', excluded, true);
  wireDetailRows();
}

async function runSelection() {
  setBusy(true);
  try {
    const data = await api(endpoint('/api/select', '/api/user/select'), { method: state.config?.user_auth_enabled ? 'POST' : 'GET' });
    state.selection = data.selection;
    state.selection.elapsed_ms = data.elapsed_ms;
    updateDataStatus(data.selection.selected || [], data.failures || []);
    renderSelection(data.selection, data.elapsed_ms);
    showNotice(t('selection_completed', { ms: data.elapsed_ms }));
    await loadOps();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderSelection(selection, elapsedMs) {
  document.getElementById('selection-meta').textContent =
    isKo()
      ? `${selection.selected.length}/${selection.max_positions}, 총 ${selection.total_size_pct}%, ${elapsedMs} ms`
      : `${selection.selected.length}/${selection.max_positions}, ${selection.total_size_pct}% in ${elapsedMs} ms`;
  const target = document.getElementById('selection');
  if (!selection.selected.length) {
    target.innerHTML = `<div class="empty-state">${t('no_eligible')}</div>`;
    return;
  }
  target.innerHTML = selection.selected.map((item, index) => `
    <article class="candidate-card clickable" data-ticker="${escapeHtml(item.ticker)}">
      <div class="candidate-top">
        <div class="ticker-lockup">
          <div class="rank">${index + 1}</div>
          <div class="ticker-symbol">${escapeHtml(item.ticker)}</div>
        </div>
        <div class="score">${item.combined_score}<small>${t('score')}</small></div>
      </div>
      <div class="candidate-meta">
        ${escapeHtml(archetypeLabel(item))} / ${escapeHtml(publicLabel(item))}
      </div>
      <ul class="reason-list">
        ${reasonItems(item).slice(0, 3).map((reason) => `<li>${escapeHtml(translateText(reason, item))}</li>`).join('')}
      </ul>
      <div class="candidate-foot">
        <span>${t('allocation_guide')} ${item.suggested_size_pct}%</span>
        <span>${escapeHtml(translateSource(item.source))} / ${escapeHtml(item.data_as_of)} / ${escapeHtml(item.scoring_version)}</span>
      </div>
    </article>
  `).join('');
  wireDetailRows();
}

async function refreshAll() {
  setBusy(true);
  try {
    await loadConfig();
    await ensureUserSession();
    await ensureStarterWatchlist();
    await Promise.all([loadWatchlist(), loadOps()]);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function bootstrap() {
  await refreshAll();
  await runScan();
  await runSelection();
}

function renderTable(targetId, items, excluded) {
  const body = document.getElementById(targetId);
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty-state">${excluded ? t('no_excluded') : t('no_actionable')}</td></tr>`;
    return;
  }
  body.innerHTML = items.map((item) => {
    const badgeClass = item.can_enter ? 'good' : item.combined_score >= 50 ? 'warn' : 'bad';
    const reason = excluded ? rejectionReason(item) : `${item.suggested_size_pct}%`;
    return `
      <tr class="clickable" data-ticker="${escapeHtml(item.ticker)}">
        <td data-label="${t('ticker')}"><strong>${escapeHtml(item.ticker)}</strong></td>
        <td data-label="${t('archetype')}">${escapeHtml(archetypeLabel(item))}</td>
        <td data-label="${t('score')}">${item.combined_score}</td>
        <td data-label="${t('status')}"><span class="badge ${badgeClass}">${escapeHtml(publicLabel(item))}</span></td>
        <td data-label="${excluded ? t('reason') : t('allocation')}">${escapeHtml(translateText(reason, item))}</td>
        <td data-label="${t('data')}">${escapeHtml(translateSource(item.source))} / ${escapeHtml(item.data_as_of)}</td>
      </tr>
    `;
  }).join('');
}

function updateDataStatus(items, failures = []) {
  const validDates = items.map((item) => item.data_as_of).filter(Boolean).sort();
  const latest = validDates.length ? validDates[validDates.length - 1] : 'not loaded';
  const providers = [...new Set(items.map((item) => item.source).filter(Boolean))];
  document.getElementById('data-as-of').textContent = `${t('data_as_of')}: ${latest}`;
  if (providers.length) {
    document.getElementById('data-source').textContent =
      `${t('provider')}: ${providers.map(translateSource).join(', ')}`;
  }
  const opsState = document.getElementById('ops-state');
  opsState.className = `status-dot ${failures.length ? 'warn' : 'good'}`;
  opsState.textContent = failures.length ? t('ops_provider_issues', { count: failures.length }) : t('ops_success');
}

function reasonItems(item) {
  const notes = [
    ...(item.rationale || []),
    ...(item.precision_notes || []),
    ...(item.warnings || [])
  ].filter(Boolean);
  if (notes.length) return notes;
  return [
    `${item.primary_archetype_label} score is ${item.combined_score}.`,
    item.can_enter ? 'Entry threshold is met.' : 'Entry threshold is not met.',
    `Allocation guide is ${item.suggested_size_pct}%.`
  ];
}

function rejectionReason(item) {
  if (item.warnings && item.warnings.length) return translateText(item.warnings[0], item);
  if (item.combined_score < 55) return translateText('Score below entry threshold.', item);
  return translateText('Monitor only.', item);
}

function findEvaluation(ticker) {
  return [...state.scan, ...((state.selection && state.selection.selected) || [])]
    .find((item) => item.ticker === ticker);
}

function wireDetailRows() {
  document.querySelectorAll('[data-ticker]').forEach((element) => {
    if (element.dataset.bound === 'true') return;
    element.dataset.bound = 'true';
    element.addEventListener('click', () => openDetailPage(element.dataset.ticker));
  });
}

function openDetailPage(ticker) {
  window.location.href = `/ticker/${encodeURIComponent(ticker)}`;
}

function openDetail(ticker) {
  const item = findEvaluation(ticker);
  if (!item) return;
  const modal = document.getElementById('detail-modal');
  const content = document.getElementById('detail-content');
  content.innerHTML = `
    <p class="eyebrow">${isKo() ? '점수 리포트' : 'Score report'}</p>
    <h2 id="detail-title">${escapeHtml(item.ticker)} <span class="muted">${escapeHtml(archetypeLabel(item))}</span></h2>
    <div class="detail-grid">
      <div class="metric-box"><span>${t('score')}</span><strong>${item.combined_score}</strong></div>
      <div class="metric-box"><span>${isKo() ? '검토 상태' : 'Review state'}</span><strong>${escapeHtml(publicLabel(item))}</strong></div>
      <div class="metric-box"><span>${t('allocation_guide')}</span><strong>${item.suggested_size_pct}%</strong></div>
      <div class="metric-box"><span>${isKo() ? '위험 기준' : 'Risk reference'}</span><strong>${item.stop_loss}</strong></div>
    </div>
    <p class="muted">
      ${t('data')}: ${escapeHtml(translateSource(item.source))} / ${escapeHtml(item.data_as_of)} /
      ${escapeHtml(translateDataQuality(item.data_quality))} / ${escapeHtml(item.scoring_version)}
    </p>
    <h3>${isKo() ? '선정 근거' : 'Rationale'}</h3>
    <ul class="reason-list">${reasonItems(item).map((reason) => `<li>${escapeHtml(translateText(reason, item))}</li>`).join('')}</ul>
  `;
  modal.hidden = false;
}

function closeDetail() {
  document.getElementById('detail-modal').hidden = true;
}

document.getElementById('add-form').addEventListener('submit', addTickers);
document.getElementById('scan-button').addEventListener('click', runScan);
document.getElementById('select-button').addEventListener('click', runSelection);
document.getElementById('refresh-button').addEventListener('click', bootstrap);
document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('detail-modal').addEventListener('click', (event) => {
  if (event.target.id === 'detail-modal') closeDetail();
});
initLanguageToggle();
bootstrap();
"""


DETAIL_JS = """
const detailState = {
  lang: localStorage.getItem('vcb_lang') || 'en',
  data: null
};

const DETAIL_I18N = {
  en: {
    ticker_analysis: 'Ticker analysis',
    dashboard: 'Dashboard',
    five_year_chart: 'Five-year price and volume',
    current_status: 'Current status',
    ai_summary: 'AI summary',
    industry_profile: 'Industry and profile',
    selection_reason: 'Selection reason',
    expert_consensus: 'Expert consensus',
    required_review: 'Required review set',
    score: 'Score',
    review_state: 'Review state',
    allocation_guide: 'Allocation guide',
    risk_reference: 'Risk reference',
    return_12w: '12w return',
    return_12m: '12m return',
    drawdown_52w: '52w drawdown',
    trend_score: 'Trend score',
    surge_score: 'Surge score',
    rs_vs_spy: 'RS vs SPY',
    intraday: 'Intraday',
    short_interest: 'Short interest',
    options_pcr: 'Options PCR',
    analyst_score: 'Analyst score',
    data_coverage: 'Data coverage',
    coverage_state: 'Coverage state',
    sector: 'Sector',
    industry: 'Industry',
    company: 'Company',
    data_note: 'Data note',
    daily_points: '{count} daily points / {freshness}',
    no_chart: 'No chart data available.',
    close_range: 'Close {min} - {max}',
    why_selected: 'Why selected',
    signals: 'Signals',
    risks: 'Risks',
    to: 'to'
  },
  ko: {
    ticker_analysis: '종목 분석',
    dashboard: '대시보드',
    five_year_chart: '최근 5년 가격과 거래량',
    current_status: '현재 상태',
    ai_summary: 'AI 요약',
    industry_profile: '업종 및 종목 정보',
    selection_reason: '종목 선정 이유',
    expert_consensus: '전문가 합의 분석',
    required_review: '필수 검토 항목',
    score: '점수',
    review_state: '검토 상태',
    allocation_guide: '배분 가이드',
    risk_reference: '위험 기준',
    return_12w: '12주 수익률',
    return_12m: '12개월 수익률',
    drawdown_52w: '52주 낙폭',
    trend_score: '추세 점수',
    surge_score: '급등 점수',
    rs_vs_spy: 'SPY 대비 상대강도',
    data_coverage: '데이터 커버리지',
    coverage_state: '커버리지 상태',
    sector: '섹터',
    industry: '업종',
    company: '기업명',
    data_note: '데이터 안내',
    daily_points: '일봉 {count}개 / {freshness}',
    no_chart: '차트 데이터가 없습니다.',
    close_range: '종가 범위 {min} - {max}'
  }
};

function t(key, values = {}) {
  const text = (DETAIL_I18N[detailState.lang] && DETAIL_I18N[detailState.lang][key]) || DETAIL_I18N.en[key] || key;
  return Object.entries(values).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, value), text);
}

function applyTranslations() {
  document.documentElement.lang = detailState.lang;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.langOption === detailState.lang);
    button.setAttribute('aria-pressed', String(button.dataset.langOption === detailState.lang));
  });
}

function setLanguage(lang) {
  detailState.lang = lang === 'ko' ? 'ko' : 'en';
  localStorage.setItem('vcb_lang', detailState.lang);
  applyTranslations();
  if (detailState.data) renderDetail(detailState.data);
}

function initLanguageToggle() {
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => setLanguage(button.dataset.langOption));
  });
  applyTranslations();
}

async function api(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error?.message || payload.message || 'Request failed');
  return payload.data;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const DETAIL_KO_DYNAMIC = {
  archetypes: {
    A_AI_TECH: 'AI/테크 메가트렌드',
    B_CRYPTO_PIVOT: '크립토 전환',
    C_QUANTUM: '퀀텀/신흥 기술',
    D_BIOTECH: '바이오 촉매',
    E_SHORT_SQUEEZE: '숏스퀴즈',
    F_PICK_SHOVEL: 'AI 인프라 수혜',
    G_TECHNICAL_MOMENTUM: '기술적 모멘텀'
  },
  publicLabels: {
    'High-priority review candidate': '우선 검토 후보',
    'Review candidate': '검토 후보',
    'Monitor only': '관찰 대상',
    'Needs review': '검토 필요',
    'High-scoring watchlist candidate': '고득점 관심 후보',
    'Watchlist candidate': '관심 후보',
    'No current setup': '현재 조건 미충족'
  },
  coverageLabels: {
    'multi-source': '다중 데이터',
    enriched: '보강 데이터',
    'price-volume-only': '가격/거래량 한정',
    insufficient: '부족',
    unknown: '알 수 없음'
  },
  sources: {
    sample: '샘플',
    'sample-placeholder': '샘플 대체값',
    yahoo: '야후',
    yahoo_chart: '야후 차트',
    stooq: '스투크',
    manual: '수동 CSV',
    finnhub: '핀허브',
    alpaca: '알파카',
    'alpaca-intraday': '알파카 장중',
    template: '템플릿',
    openai: 'OpenAI',
    local: '로컬'
  },
  dataQuality: {
    offline: '오프라인',
    'eod-market': '일봉 시장 데이터',
    'partial-eod-market': '부분 일봉 시장 데이터',
    'thin-eod-market': '부족한 일봉 시장 데이터',
    'stale-eod-market': '오래된 일봉 시장 데이터'
  },
  consensusRoles: {
    Quant: '퀀트',
    Risk: '리스크',
    Product: '프로덕트'
  },
  consensusTitles: {
    'Score and trend state': '점수와 추세 상태',
    'Risk reference': '위험 기준',
    'Selection reason': '선정 이유'
  }
};

function isDetailKo() {
  return detailState.lang === 'ko';
}

function detailArchetypeLabel(item) {
  if (!isDetailKo()) return item.primary_archetype_label;
  return DETAIL_KO_DYNAMIC.archetypes[item.primary_archetype] || item.primary_archetype_label;
}

function detailPublicLabel(item) {
  const label = item.public_label || item.decision_label || item.status || 'Needs review';
  return isDetailKo() ? DETAIL_KO_DYNAMIC.publicLabels[label] || label : label;
}

function detailCoverageLabel(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.coverageLabels[value] || value || '-' : value || '-';
}

function detailSource(value) {
  if (!isDetailKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => DETAIL_KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function detailDataQuality(value) {
  if (!isDetailKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => DETAIL_KO_DYNAMIC.dataQuality[part] || DETAIL_KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function detailMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function detailText(value, item = {}) {
  const text = String(value || '');
  if (!isDetailKo() || !text) return text;
  let match = text.match(/^Primary archetype is (.+) with base score ([-0-9.]+)\.$/);
  if (match) return `주요 유형은 ${detailArchetypeLabel(item)}이며 기본 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Complexity modifier is ([-0-9.]+); combined score is ([-0-9.]+)\.$/);
  if (match) return `복합 보정값은 ${match[1]}점이며 최종 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Data quality: (.+)\.$/);
  if (match) return `데이터 품질: ${detailDataQuality(match[1])}.`;
  match = text.match(/^Trend template score: ([-0-9.]+)\/100\.$/);
  if (match) return `추세 템플릿 점수: 100점 만점에 ${match[1]}점.`;
  match = text.match(/^Surge score: ([-0-9.]+)\/100\.$/);
  if (match) return `급등 점수: 100점 만점에 ${match[1]}점.`;
  match = text.match(/^Data coverage: ([-0-9.]+)\/100 \(([^)]+)\)\. (.+)$/);
  if (match) return `데이터 커버리지: 100점 만점에 ${match[1]}점(${detailCoverageLabel(match[2])}). ${detailText(match[3], item)}`;
  match = text.match(/^Missing: (.+)\.$/);
  if (match) return `누락 데이터: ${detailMissingList(match[1])}.`;
  match = text.match(/^Research enrichment applied from (.+) as of (.+)\.$/);
  if (match) return `리서치 보강 데이터가 ${detailSource(match[1])}에서 적용되었습니다. 기준일: ${match[2]}.`;
  match = text.match(/^Intraday quote layer: (.+) price (.+) as of (.+)\.$/);
  if (match) return `장중 시세 계층: ${detailSource(match[1])} 가격 ${match[2]}, 기준 시각 ${match[3]}.`;
  match = text.match(/^Composite score is above the internal review threshold\.$/);
  if (match) return '종합 점수가 내부 검토 기준을 넘었습니다.';
  match = text.match(/^12-week momentum is positive at (.+)%\.$/);
  if (match) return `12주 모멘텀이 +${match[1]}%로 양호합니다.`;
  match = text.match(/^Analyst\/revision score is positive at (.+)\.$/);
  if (match) return `애널리스트/추정치 수정 점수가 ${match[1]}점으로 양호합니다.`;
  match = text.match(/^Call open interest is greater than put open interest\.$/);
  if (match) return '콜 옵션 미결제약정이 풋 옵션보다 큽니다.';
  match = text.match(/^Short interest is elevated at (.+)%\.$/);
  if (match) return `공매도 비율이 ${match[1]}%로 높습니다.`;
  const exact = {
    'Score is above the MVP portfolio-manager threshold of 55.': '점수가 MVP 포트폴리오 관리 기준인 55점을 넘었습니다.',
    'Score passed the numeric threshold, but final selection is blocked until enrichment data is present.':
      '점수 기준은 통과했지만 보강 데이터가 없어서 최종 선정은 보류됩니다.',
    'Score is below the MVP portfolio-manager threshold of 55; wait.': '점수가 MVP 포트폴리오 관리 기준인 55점보다 낮아 대기합니다.',
    'Decision support only; not investment advice.': '의사결정 보조 정보일 뿐 투자 자문이 아닙니다.',
    'No automatic trading is performed.': '자동 매매는 실행하지 않습니다.',
    'Result uses sample/offline data, not live market data.': '이 결과는 실시간 시장 데이터가 아니라 샘플/오프라인 데이터를 사용합니다.',
    'High-volatility archetype: avoid stacking multiple simultaneous positions.':
      '고변동성 유형입니다. 같은 시점에 여러 고변동성 포지션을 겹치지 않도록 검토하세요.',
    ['Market-data provider supplies EOD price/volume only; '
      + 'fundamentals and catalysts remain unavailable unless research data is configured.']:
      '시장 데이터 제공자는 일봉 가격/거래량만 제공합니다. 리서치 데이터가 설정되지 않으면 재무와 촉매 데이터는 비어 있습니다.',
    'Required market, fundamental, catalyst, and positioning groups present.': '시장, 재무, 촉매, 포지셔닝 데이터 그룹이 모두 존재합니다.',
    'Data coverage is below the final-selection gate.': '데이터 커버리지가 최종 선정 기준보다 낮습니다.',
    'Current provider supplies end-of-day/delayed chart data, not tick-by-tick real-time data.':
      '현재 제공자는 틱 단위 실시간 데이터가 아니라 일봉/지연 차트 데이터를 제공합니다.',
    'No selection rationale is available for this ticker.': '이 종목의 선정 근거가 없습니다.'
  };
  return exact[text] || text;
}

function tickerFromPath() {
  const parts = window.location.pathname.split('/').filter(Boolean);
  return decodeURIComponent(parts[1] || '').toUpperCase();
}

function showDetailNotice(message, error = false) {
  const box = document.getElementById('detail-notice');
  box.hidden = false;
  box.className = `notice${error ? ' error' : ''}`;
  box.textContent = message;
}

async function bootstrapDetail() {
  const ticker = tickerFromPath();
  try {
    const data = await api(`/api/ticker-analysis?ticker=${encodeURIComponent(ticker)}`);
    detailState.data = data;
    renderDetail(data);
  } catch (error) {
    showDetailNotice(error.message, true);
  }
}

function renderDetail(data) {
  const evaluation = data.evaluation;
  const profile = data.profile;
  const history = data.history;
  document.title = isDetailKo() ? `${data.ticker} 분석 - VCB-Alt` : `${data.ticker} Analysis - VCB-Alt`;
  document.getElementById('detail-symbol').textContent = `${data.ticker} ${profile.company_name}`;
  document.getElementById('detail-provider').textContent = `${detailSource(history.source)} / ${history.range}`;
  document.getElementById('chart-meta').textContent =
    t('daily_points', { count: history.points.length, freshness: detailDataQuality(history.freshness) });
  document.getElementById('review-state').textContent = detailPublicLabel(evaluation);
  document.getElementById('score-version').textContent = evaluation.scoring_version;
  document.getElementById('profile-source').textContent = profile.profile_source;
  renderChart(history.points);
  renderStatusGrid(evaluation, data.metrics || {});
  renderAiSummary(data.ai_summary || {});
  renderProfile(profile, history);
  renderRationale(evaluation);
  renderConsensus(data.expert_consensus);
}

function renderStatusGrid(item, metrics) {
  document.getElementById('status-grid').innerHTML = `
    <div class="metric-box"><span>${t('score')}</span><strong>${item.combined_score}</strong></div>
    <div class="metric-box"><span>${t('review_state')}</span><strong>${escapeHtml(detailPublicLabel(item))}</strong></div>
    <div class="metric-box"><span>${t('allocation_guide')}</span><strong>${item.suggested_size_pct}%</strong></div>
    <div class="metric-box"><span>${t('risk_reference')}</span><strong>${item.stop_loss}</strong></div>
    <div class="metric-box"><span>${t('return_12w')}</span><strong>${metric(metrics, 'return_12w_pct')}%</strong></div>
    <div class="metric-box"><span>${t('return_12m')}</span><strong>${metric(metrics, 'return_12m_pct')}%</strong></div>
    <div class="metric-box"><span>${t('drawdown_52w')}</span><strong>${metric(metrics, 'drawdown_52w_pct')}%</strong></div>
    <div class="metric-box"><span>${t('trend_score')}</span><strong>${metric(metrics, 'trend_template_score')}</strong></div>
    <div class="metric-box"><span>${t('surge_score')}</span><strong>${metric(metrics, 'surge_score')}</strong></div>
    <div class="metric-box"><span>${t('rs_vs_spy')}</span><strong>${metric(metrics, 'relative_strength_12w_pp')}pp</strong></div>
    <div class="metric-box"><span>${t('intraday')}</span><strong>${metric(metrics, 'intraday_price')}</strong></div>
    <div class="metric-box"><span>${t('short_interest')}</span><strong>${metric(metrics, 'short_interest_pct')}%</strong></div>
    <div class="metric-box"><span>${t('options_pcr')}</span><strong>${metric(metrics, 'put_call_ratio')}</strong></div>
    <div class="metric-box"><span>${t('analyst_score')}</span><strong>${metric(metrics, 'analyst_revision_score')}</strong></div>
    <div class="metric-box"><span>${t('data_coverage')}</span><strong>${item.data_coverage_score}/100</strong></div>
    <div class="metric-box">
      <span>${t('coverage_state')}</span><strong>${escapeHtml(detailCoverageLabel(item.data_coverage_label))}</strong>
    </div>
  `;
}

function metric(values, key) {
  return values[key] ?? '-';
}

function renderProfile(profile, history) {
  const metrics = detailState.data?.metrics || {};
  const intradayError = metrics.intraday_error
    ? `<p><strong>${t('intraday')}:</strong> ${escapeHtml(detailText(metrics.intraday_error))}</p>`
    : '';
  document.getElementById('profile-body').innerHTML = `
    <p><strong>${t('sector')}:</strong> ${escapeHtml(profile.sector)}</p>
    <p><strong>${t('industry')}:</strong> ${escapeHtml(profile.industry)}</p>
    <p><strong>${t('company')}:</strong> ${escapeHtml(profile.company_name)}</p>
    <p><strong>${t('data_note')}:</strong> ${escapeHtml(detailText(history.realtime_note))}</p>
    ${intradayError}
  `;
}

function renderAiSummary(summary) {
  const data = detailState.data || {};
  const evaluation = data.evaluation || {};
  const profile = data.profile || {};
  document.getElementById('ai-provider').textContent =
    `${detailSource(summary.provider || 'template')} / ${detailSource(summary.model || 'local')}`;
  const why = Array.isArray(summary.why_selected) ? summary.why_selected : [];
  const positives = Array.isArray(summary.positive_signals) ? summary.positive_signals : [];
  const risks = Array.isArray(summary.risk_flags) ? summary.risk_flags : [];
  const headline = isDetailKo()
    ? `${data.ticker || ''}는 ${detailPublicLabel(evaluation)} 상태입니다.`
    : (summary.headline || '');
  const body = isDetailKo()
    ? `${detailArchetypeLabel(evaluation)} 유형이며 종합 점수는 ${evaluation.combined_score ?? '-'}점입니다. `
      + `업종은 ${profile.sector || '-'} / ${profile.industry || '-'}입니다.`
    : (summary.summary || '');
  document.getElementById('ai-summary-body').innerHTML = `
    <p><strong>${escapeHtml(headline)}</strong></p>
    <p>${escapeHtml(body)}</p>
    <h3>${t('why_selected')}</h3>
    <ul>${why.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
    <h3>${t('signals')}</h3>
    <ul>${positives.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
    <h3>${t('risks')}</h3>
    <ul>${risks.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
  `;
}

function renderRationale(item) {
  const reasons = [...(item.rationale || []), ...(item.precision_notes || []), ...(item.warnings || [])];
  document.getElementById('rationale-body').innerHTML =
    `<ul>${reasons.map((reason) => `<li>${escapeHtml(detailText(reason, item))}</li>`).join('')}</ul>`;
}

function renderConsensus(items) {
  document.getElementById('consensus-body').innerHTML = items.map((item) => `
    <p>
      <strong>${escapeHtml(consensusRole(item.role))} - ${escapeHtml(consensusTitle(item.title))}:</strong>
      ${escapeHtml(consensusBody(item))}
    </p>
  `).join('');
}

function consensusRole(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.consensusRoles[value] || value : value;
}

function consensusTitle(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.consensusTitles[value] || value : value;
}

function consensusBody(item) {
  if (!isDetailKo()) return item.body;
  if (item.role === 'Quant') {
    return `종합 점수는 ${detailState.data.evaluation.combined_score}점이며 `
      + `${detailState.data.evaluation.scoring_version} 기준입니다. 실행 전 추세와 급등 지표를 함께 검토하세요.`;
  }
  if (item.role === 'Risk') {
    return '위험 기준과 배분 가이드는 매매 지시가 아니라 검토 입력값으로 사용하세요.';
  }
  if (item.role === 'Product') {
    return '첫 번째 근거 항목들이 이 종목이 검토 목록에 오른 주요 이유를 설명합니다.';
  }
  return item.body;
}

function renderChart(points) {
  const svg = document.getElementById('price-chart');
  if (!points.length) {
    svg.innerHTML = `<text x="20" y="40" fill="#a4ada9">${t('no_chart')}</text>`;
    return;
  }
  const width = 900;
  const height = 420;
  const pad = 42;
  const closes = points.map((point) => point.close);
  const volumes = points.map((point) => point.volume);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const maxVolume = Math.max(...volumes);
  const x = (index) => pad + (index / Math.max(1, points.length - 1)) * (width - pad * 2);
  const yPrice = (value) => height - pad - ((value - minClose) / Math.max(1, maxClose - minClose)) * (height - pad * 2);
  const yVolume = (value) => height - pad - (value / Math.max(1, maxVolume)) * 88;
  const line = points.map((point, index) => `${x(index)},${yPrice(point.close)}`).join(' ');
  const bars = points.filter((_, index) => index % Math.ceil(points.length / 120) === 0).map((point, index) => {
    const actualIndex = index * Math.ceil(points.length / 120);
    const barX = x(actualIndex);
    return `<line x1="${barX}" y1="${height - pad}" x2="${barX}" y2="${yVolume(point.volume)}" stroke="#2f5748" stroke-width="2" />`;
  }).join('');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="#0c0f0e" rx="8"></rect>
    <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#2b3430"></line>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" stroke="#2b3430"></line>
    ${bars}
    <polyline points="${line}" fill="none" stroke="#82d6b4" stroke-width="3"></polyline>
    <text x="${pad}" y="24" fill="#e6e8e6" font-size="14">${t('close_range', { min: minClose.toFixed(2), max: maxClose.toFixed(2) })}</text>
    <text x="${width - pad - 180}" y="${height - 14}" fill="#a4ada9" font-size="12">
      ${escapeHtml(points[0].date)} ${t('to')} ${escapeHtml(points[points.length - 1].date)}
    </text>
  `;
}

initLanguageToggle();
bootstrapDetail();
"""

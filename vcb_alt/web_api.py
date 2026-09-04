"""JSON API handlers for the web layer.

Everything that turns a parsed request into an OperationResult: scanning, selection,
tenant endpoints, ticker analysis, release/provider status and the operator routes.
web.py owns the server, routing and HTTP transport around this module.

Split out of web.py; behaviour is unchanged.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from urllib.parse import parse_qs

from .ai_summary import build_ai_summary
from .auth import public_user
from .config import AppConfig, doctor_report
from .db import (
    add_watchlist,
    connect,
    ensure_initialized,
    list_watchlist,
    log_operation,
    recent_failures,
    recent_logs,
    recent_provider_alerts,
    record_failure,
    record_provider_alert,
    remove_watchlist,
    save_evaluation,
)
from .errors import AppError, UnauthorizedError, ValidationError
from .job_queue import (
    enqueue_or_get_market_scan_snapshot,
    enqueue_scan_job,
    get_market_scan_job,
    get_scan_job,
    list_scan_jobs,
    public_market_scan_job,
    public_market_scan_outcome,
    queue_status,
    run_queued_scan_jobs,
    validate_job_limit,
)
from .market_universe import diagnose_alpaca_credentials, scan_market_universe, scan_pipeline_readiness
from .models import OperationResult, SCORING_VERSION
from .portfolio import select_portfolio
from .provider_resilience import provider_alert_payload, provider_health_report
from .providers import get_price_history, get_snapshot, get_ticker_profile, provider_status
from .saas_readiness import get_saas_readiness
from .scoring import evaluate_snapshot
from .sample_data import SAMPLE_TICKERS
from .tenant_store import (
    add_user_watchlist,
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
from .web_auth import (
    bearer_token,
    is_global_operator,
    production_saas_ready,
    require_worker_token,
)
from .validation import validate_ticker


def _require_operator_view(config: AppConfig, conn: Any, headers: dict[str, str] | None) -> None:
    """Guard the cross-tenant operator views: /api/logs and /api/failures.

    These are not tenant data - the worker records its own failure messages there - and
    they are not in LEGACY_GLOBAL_API_PATHS, so SaaS mode left them reachable by anyone.
    The shared deployment token does not cover them either: production runs with
    public_web_enabled=false, which switches that gate off entirely, so on a deployed
    site the only thing in front of them was nothing at all.

    Single-operator local mode is unchanged: there the server is the operator's own
    machine and the dashboard reads these directly.
    """
    if not config.user_auth_enabled:
        return
    user = require_user(conn, bearer_token(headers or {}))
    if not is_global_operator(config, user):
        raise UnauthorizedError("Operator logs require a global operator account.")


LEGACY_GLOBAL_API_PATHS = {
    "/api/watchlist": "/api/user/watchlist",
    "/api/scan": "/api/user/scan",
    "/api/select": "/api/user/select",
}


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
        report = doctor_report(config)
        try:
            with connect(config) as conn:
                report["scan_pipeline"] = scan_pipeline_readiness(config, conn)
        except AppError:
            report["scan_pipeline"] = scan_pipeline_readiness(config)
        return OperationResult.success("Configuration loaded.", report)
    if method == "GET" and path == "/api/provider-status":
        return OperationResult.success("Provider status loaded.", provider_status(config))
    if method == "GET" and path == "/api/provider-health":
        return OperationResult.success("Provider health loaded.", provider_health_report(config))
    if method == "GET" and path == "/api/provider-diagnostics/alpaca":
        symbol = parse_qs(query).get("symbol", ["AAPL"])[0]
        return OperationResult.success("Alpaca diagnostics loaded.", diagnose_alpaca_credentials(config, symbol=symbol))
    if method == "GET" and path == "/api/release-status":
        return OperationResult.success("Release status loaded.", _release_status(config))
    if method == "GET" and path == "/api/ticker-analysis":
        ticker = parse_qs(query).get("ticker", [""])[0]
        return OperationResult.success("Ticker analysis loaded.", _ticker_analysis(config, ticker))
    if method == "GET" and path == "/api/saas-readiness":
        return OperationResult.success("SaaS readiness checked.", get_saas_readiness())
    if method in {"GET", "POST"} and path == "/api/admin/run-worker":
        if config.production_saas_mode and method != "POST":
            raise ValidationError("Production worker trigger requires POST.")
        if not config.worker_cron_enabled:
            return OperationResult.success("Worker cron is disabled.", {"processed": 0, "failed": 0, "disabled": True})
        require_worker_token(config, query, headers or {})
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
            user = require_user(conn, bearer_token(headers or {}))
            return OperationResult.success("User loaded.", public_user(user))
        if method == "GET" and path == "/api/user/export":
            user = require_user(conn, bearer_token(headers or {}))
            return OperationResult.success("User data exported.", export_user_data(conn, user))
        if method == "DELETE" and path == "/api/user/account":
            user = require_user(conn, bearer_token(headers or {}))
            confirm = parse_qs(query).get("confirm", [""])[0]
            return OperationResult.success("User account deleted.", delete_user_account(conn, user, confirm))
        if path == "/api/user/watchlist":
            user = require_user(conn, bearer_token(headers or {}))
            if method == "GET":
                items = list_user_watchlist(conn, user)
                return OperationResult.success(
                    "User watchlist loaded.",
                    {
                        "items": items,
                        "count": len(items),
                        "metadata": _watchlist_metadata(config),
                    },
                )
            if method == "POST":
                body = payload or {}
                raw = body.get("tickers") or body.get("ticker")
                tickers = raw.replace(",", " ").split() if isinstance(raw, str) else [str(item) for item in raw or []]
                data = add_user_watchlist(conn, user, tickers)
                data["metadata"] = _watchlist_metadata(config)
                return OperationResult.success(
                    "User watchlist updated.",
                    data,
                    status_code=201,
                )
            if method == "DELETE":
                ticker = parse_qs(query).get("ticker", [""])[0]
                data = remove_user_watchlist(conn, user, ticker)
                data["metadata"] = _watchlist_metadata(config)
                return OperationResult.success("User watchlist updated.", data)
        if path == "/api/jobs/scan" and method == "POST":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, bearer_token(headers or {}))
            if config.scan_mode == "market_universe":
                outcome = enqueue_or_get_market_scan_snapshot(config, conn, user)
                if outcome["state"] == "fresh":
                    return OperationResult.success("Fresh market scan snapshot loaded.", outcome["report"])
                return OperationResult.success(
                    "Market scan snapshot queued.", public_market_scan_outcome(outcome), status_code=202
                )
            return OperationResult.success("Scan job queued.", enqueue_scan_job(conn, user), status_code=202)
        if path == "/api/user/scan" and method in {"GET", "POST"}:
            if not config.user_auth_enabled:
                raise ValidationError("User authentication is not enabled.")
            user = require_user(conn, bearer_token(headers or {}))
            return _scan_user(config, conn, user)
        if path == "/api/user/select" and method in {"GET", "POST"}:
            if not config.user_auth_enabled:
                raise ValidationError("User authentication is not enabled.")
            user = require_user(conn, bearer_token(headers or {}))
            if config.scan_mode == "market_universe":
                # Rebuild from the finished scan instead of running it again.
                return _scan_user(config, conn, user, message="Selection completed.", cached_only=True)
            evaluations, failures, elapsed_ms = _evaluate_user_watchlist(config, conn, user)
            selection = select_portfolio(evaluations)
            return OperationResult.success(
                "Selection completed.",
                {"selection": selection.to_dict(), "failures": failures, "elapsed_ms": elapsed_ms},
            )
        if path == "/api/jobs" and method == "GET":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, bearer_token(headers or {}))
            jobs = list_scan_jobs(conn, user)
            return OperationResult.success("Scan jobs loaded.", {"items": jobs, "count": len(jobs)})
        if path.startswith("/api/jobs/market-scan/") and method == "GET":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            require_user(conn, bearer_token(headers or {}))
            job_id = path.removeprefix("/api/jobs/market-scan/")
            return OperationResult.success("Market scan job loaded.", public_market_scan_job(get_market_scan_job(conn, job_id)))
        if path.startswith("/api/jobs/") and method == "GET":
            if not config.user_auth_enabled or not config.scan_queue_enabled:
                raise ValidationError("Scan queue is not enabled.")
            user = require_user(conn, bearer_token(headers or {}))
            job_id = path.removeprefix("/api/jobs/")
            return OperationResult.success("Scan job loaded.", get_scan_job(conn, user, job_id))
        if method == "GET" and path == "/api/admin/users":
            user = require_role(require_user(conn, bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Tenant users loaded.", {"items": list_tenant_users(conn, user)})
        if method == "GET" and path == "/api/admin/audit-events":
            user = require_role(require_user(conn, bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Audit events loaded.", {"items": list_audit_events(conn, user)})
        if method == "GET" and path == "/api/admin/queue-status":
            user = require_role(require_user(conn, bearer_token(headers or {})), {"owner", "admin"})
            return OperationResult.success("Queue status loaded.", queue_status(conn, user["tenant_id"]))
        if method == "GET" and path == "/api/admin/provider-alerts":
            user = require_user(conn, bearer_token(headers or {}))
            limit = int(parse_qs(query).get("limit", ["20"])[0])
            if is_global_operator(config, user):
                visibility = "global_operator"
                items = recent_provider_alerts(conn, max(1, min(limit, 100)), include_global=True)
            else:
                require_role(user, {"owner", "admin"})
                visibility = "tenant_scoped"
                items = recent_provider_alerts(conn, max(1, min(limit, 100)), tenant_id=user["tenant_id"])
            return OperationResult.success(
                "Provider alerts loaded.",
                {"items": items, "visibility": visibility},
            )
        if config.user_auth_enabled and path in LEGACY_GLOBAL_API_PATHS:
            return _legacy_global_api_result(path)
        if method == "GET" and path == "/api/watchlist":
            items = list_watchlist(conn)
            return OperationResult.success(
                "Watchlist loaded.",
                {
                    "items": items,
                    "count": len(items),
                    "metadata": _watchlist_metadata(config),
                },
            )
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
            data["metadata"] = _watchlist_metadata(config)
            log_operation(conn, "web watchlist add", "success", "Watchlist updated.", data)
            return OperationResult.success("Watchlist updated.", data, status_code=201)
        if method == "DELETE" and path == "/api/watchlist":
            ticker = parse_qs(query).get("ticker", [""])[0]
            data = remove_watchlist(conn, [validate_ticker(ticker)])
            data["metadata"] = _watchlist_metadata(config)
            log_operation(conn, "web watchlist remove", "success", "Watchlist updated.", data)
            return OperationResult.success("Watchlist updated.", data)
        if method == "GET" and path == "/api/scan":
            return _scan(config, conn)
        if method == "GET" and path == "/api/select":
            if config.scan_mode == "market_universe":
                # Rebuild from the finished scan instead of running it again.
                return _scan(config, conn, message="Selection completed.", cached_only=True)
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
            _require_operator_view(config, conn, headers)
            items = recent_logs(conn, 12)
            return OperationResult.success("Logs loaded.", {"items": items, "count": len(items)})
        if method == "GET" and path == "/api/failures":
            _require_operator_view(config, conn, headers)
            items = recent_failures(conn, 12)
            return OperationResult.success("Failures loaded.", {"items": items, "count": len(items)})
    raise ValidationError("API route not found.")


def _scan(config: AppConfig, conn: Any, *, message: str = "Scan completed.", cached_only: bool = False) -> OperationResult:
    if config.scan_mode == "market_universe":
        report = scan_market_universe(config, conn=conn, cached_only=cached_only)
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


def _scan_user(
    config: AppConfig,
    conn: Any,
    user: dict[str, Any],
    *,
    message: str = "Scan completed.",
    cached_only: bool = False,
) -> OperationResult:
    if config.scan_mode == "market_universe":
        if config.production_saas_mode and config.scan_queue_enabled:
            outcome = enqueue_or_get_market_scan_snapshot(config, conn, user)
            if outcome["state"] == "fresh":
                return OperationResult.success("Fresh market scan snapshot loaded.", outcome["report"])
            return OperationResult.success(
                "Market scan snapshot queued.", public_market_scan_outcome(outcome), status_code=202
            )
        report = scan_market_universe(config, conn=conn, cached_only=cached_only)
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
            _record_provider_alert_if_needed(conn, exc, "legacy_watchlist_scan", failure)
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
            failure = {"ticker": ticker, "code": exc.code, "message": exc.message}
            _record_provider_alert_if_needed(conn, exc, "tenant_watchlist_scan", failure, tenant_id=user["tenant_id"])
            failures.append(failure)
    conn.commit()
    elapsed_ms = int((perf_counter() - start) * 1000)
    return evaluations, failures, elapsed_ms


def _record_provider_alert_if_needed(
    conn: Any,
    exc: BaseException,
    context: str,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
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
        tenant_id=tenant_id,
    )


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
        "production_saas_ready": production_saas_ready(config),
        "public_scope": "Single-operator/token-protected preview, not unrestricted public SaaS.",
        "configured_data": {
            "market_provider": status.get("provider"),
            "research_provider": status.get("research_data_provider"),
            "research_ready": live_research_ready,
            "intraday_provider": status.get("intraday_data_provider"),
            "intraday_ready": live_intraday_ready,
            "ai_summary_provider": status.get("ai_summary_provider"),
            "summary_provider_label": status.get("summary_provider_label"),
            "summary_role": status.get("summary_role"),
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
            "Open ticker detail pages with five-year charts, sector/industry, rationale, and explanation summary.",
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
        "analyst_positive_rating_count": getattr(snapshot, "analyst_buy_count", 0),
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
                f"{evaluation['scoring_version']}; review the trend and surge metrics as research context."
            ),
        },
        {
            "role": "Risk",
            "title": "Risk marker",
            "body": "Use the risk marker and research size reference as review inputs, not trade instructions.",
        },
        {
            "role": "Product",
            "title": "Selection reason",
            "body": "The first rationale bullets explain the main reason this ticker reached the review list.",
        },
    ]


def _watchlist_metadata(config: AppConfig) -> dict[str, Any]:
    market_wide_primary = config.scan_mode == "market_universe"
    starter_helper_available = market_wide_primary or config.production_saas_mode
    return {
        "purpose": "optional_manual_research",
        "core_flow": "market_wide_discovery" if market_wide_primary else "manual_watchlist_research",
        "market_wide_discovery_primary": market_wide_primary,
        "starter_seeded": _should_auto_seed_watchlist(config),
        "starter_helper_available": starter_helper_available,
        "result_boundary": (
            "Market-wide candidates come from the scan snapshot endpoint, not from the manual watchlist."
            if market_wide_primary
            else "Manual watchlist is the active local/private research input."
        ),
        "starter_helper": {
            "mode": "optional_onboarding_helper" if starter_helper_available else "legacy_auto_seed",
            "tickers": list(SAMPLE_TICKERS) if starter_helper_available else [],
            "description": (
                "Optional starter tickers populate only the manual research drawer."
                if starter_helper_available
                else "Local legacy watchlist auto-seeding may be enabled."
            ),
        },
        "description": (
            "Manual watchlist is an optional research drawer. It is not the market-wide discovery result."
            if market_wide_primary
            else "Manual watchlist is the active local/private research input."
        ),
    }


def _legacy_global_api_result(path: str) -> OperationResult:
    target = LEGACY_GLOBAL_API_PATHS.get(path, "/api/user/*")
    return OperationResult.failure(
        f"Legacy global endpoint {path} is disabled in SaaS mode. Use {target} with a tenant session instead.",
        status_code=410,
        code="LEGACY_ENDPOINT_GONE",
        detail=(
            "Migration required: user_auth_enabled=true routes must use tenant-scoped /api/user/* APIs "
            "or durable market-snapshot job/status APIs. The legacy global watchlist/scan/select endpoints "
            "are local/private-mode only."
        ),
    )


def _should_auto_seed_watchlist(config: AppConfig) -> bool:
    return bool(config.auto_seed_sample and config.scan_mode != "market_universe" and not config.production_saas_mode)

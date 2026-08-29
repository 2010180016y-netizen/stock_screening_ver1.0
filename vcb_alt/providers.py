from __future__ import annotations

import csv
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import replace
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import AppConfig
from .errors import AppError, NotFoundError, ValidationError
from .models import StockSnapshot
from .provider_resilience import ProviderFailure, provider_request_json, provider_request_text
from .sample_data import get_snapshot as get_sample_snapshot
from .validation import validate_ticker

BOOL_FIELDS = {
    "forward_guidance_raised",
    "above_200dma",
    "news_catalyst_30d",
    "fda_milestone_90d",
    "data_center_narrative",
    "filing_catalyst_30d",
}

INT_FIELDS = {
    "insider_buy_count_90d",
    "analyst_buy_count",
    "analyst_hold_count",
    "analyst_sell_count",
    "news_headline_count_30d",
}

TEXT_FIELDS = {
    "ticker",
    "company_name",
    "source",
    "data_as_of",
    "data_quality",
    "enrichment_source",
    "enrichment_as_of",
    "data_coverage_label",
    "data_coverage_detail",
    "latest_filing_date",
    "latest_filing_type",
    "latest_filing_url",
    "intraday_source",
    "intraday_as_of",
    "intraday_error",
}

SNAPSHOT_FIELDS = {field.name for field in fields(StockSnapshot)}
ENRICHMENT_FIELDS = SNAPSHOT_FIELDS - {
    "ticker",
    "company_name",
    "price",
    "source",
    "data_as_of",
    "data_quality",
    "return_12w_pct",
    "return_12m_pct",
    "drawdown_52w_pct",
    "price_vs_50dma_pct",
    "price_vs_150dma_pct",
    "price_vs_200dma_pct",
    "trend_template_score",
    "surge_score",
    "rr_ratio",
    "breakout_volume_ratio",
    "drawdown_recovery_pct",
    "above_200dma",
    "volume_z_score_30d",
    "sector_rs_12w_pp",
    "data_coverage_score",
    "data_coverage_label",
    "data_coverage_detail",
    "intraday_price",
    "intraday_change_pct",
    "intraday_volume",
    "intraday_source",
    "intraday_as_of",
    "intraday_freshness_seconds",
    "intraday_error",
}
STOOQ_BASE_URL = "https://stooq.com/q/d/l/"
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
STOOQ_CACHE_VERSION = "v1"
RESEARCH_CACHE_VERSION = "v1"
INTRADAY_CACHE_VERSION = "v1"
SEC_CACHE_VERSION = "v1"

PROFILE_OVERRIDES = {
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
    "GME": {"sector": "Consumer Cyclical", "industry": "Specialty Retail"},
    "MSTR": {"sector": "Technology", "industry": "Software - Application"},
    "PLTR": {"sector": "Technology", "industry": "Software - Infrastructure"},
    "RGTI": {"sector": "Technology", "industry": "Computer Hardware / Quantum Computing"},
    "SMMT": {"sector": "Healthcare", "industry": "Biotechnology"},
    "VST": {"sector": "Utilities", "industry": "Independent Power Producers"},
    "SPY": {"sector": "ETF", "industry": "Large-Cap US Equity ETF"},
}

PROVIDER_CAPABILITIES = {
    "sample": {
        "mode": "offline",
        "market_data": False,
        "fundamentals": True,
        "price_volume": False,
        "requires_external_api": False,
    },
    "manual": {
        "mode": "operator_csv",
        "market_data": False,
        "fundamentals": True,
        "price_volume": True,
        "requires_external_api": False,
    },
    "stooq": {
        "mode": "eod_market_data",
        "market_data": True,
        "fundamentals": False,
        "price_volume": True,
        "supports_manual_enrichment": True,
        "supports_research_api_enrichment": False,
        "requires_external_api": True,
    },
    "yahoo": {
        "mode": "eod_market_data",
        "market_data": True,
        "fundamentals": False,
        "price_volume": True,
        "supports_manual_enrichment": True,
        "supports_research_api_enrichment": False,
        "requires_external_api": True,
    },
    "yahoo_chart": {
        "mode": "eod_market_data",
        "market_data": True,
        "fundamentals": False,
        "price_volume": True,
        "supports_manual_enrichment": True,
        "supports_research_api_enrichment": False,
        "requires_external_api": True,
    },
}

RESEARCH_PROVIDER_CAPABILITIES = {
    "csv": {
        "fundamentals": True,
        "earnings": True,
        "news": True,
        "short_interest": True,
        "options": True,
        "analyst_revisions": False,
        "filings": False,
        "requires_credential": False,
    },
    "finnhub": {
        "fundamentals": True,
        "earnings": True,
        "news": True,
        "short_interest": True,
        "options": True,
        "analyst_revisions": True,
        "filings": True,
        "requires_credential": True,
    },
    "finnhub_csv": {
        "fundamentals": True,
        "earnings": True,
        "news": True,
        "short_interest": True,
        "options": True,
        "analyst_revisions": True,
        "filings": True,
        "requires_credential": True,
        "csv_override": True,
    },
}


@dataclass(frozen=True)
class MarketBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def get_snapshot(config: AppConfig, ticker_value: str) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    if config.data_provider == "sample":
        return get_sample_snapshot(ticker)
    if config.data_provider == "manual":
        return get_manual_snapshot(config, ticker)
    if config.data_provider == "stooq" and config.external_api_enabled:
        return get_stooq_snapshot(config, ticker)
    if config.data_provider in {"yahoo", "yahoo_chart"} and config.external_api_enabled:
        return get_yahoo_snapshot(config, ticker)
    if config.external_api_enabled:
        raise NotFoundError(f"Provider '{config.data_provider}' is configured but not implemented.")
    raise ValidationError(f"Unsupported data provider: {config.data_provider}")


def provider_status(config: AppConfig) -> dict[str, Any]:
    provider = "yahoo" if config.data_provider == "yahoo_chart" else config.data_provider
    capabilities = PROVIDER_CAPABILITIES.get(config.data_provider, {})
    research_capabilities = RESEARCH_PROVIDER_CAPABILITIES.get(config.research_data_provider, {})
    warnings: list[str] = []
    enrichment_path = enrichment_snapshot_path(config)
    enrichment_available = enrichment_path.exists()
    if config.data_provider in {"yahoo", "yahoo_chart", "stooq"} and not config.external_api_enabled:
        warnings.append("External API access is disabled; this provider cannot fetch fresh market data.")
    if config.scan_mode == "market_universe" and not (
        config.external_api_enabled and config.alpaca_api_key and config.alpaca_api_secret
    ):
        warnings.append("Market-universe scan needs Alpaca assets and stock snapshots for live all-market discovery.")
    research_provider_available = enrichment_available or (
        config.research_data_provider.startswith("finnhub") and bool(config.finnhub_api_key)
    )
    if capabilities.get("price_volume") and not capabilities.get("fundamentals") and not research_provider_available:
        warnings.append("Provider supplies price/volume only; configure research data or CSV enrichment for final selection.")
    if capabilities.get("supports_manual_enrichment") and not research_provider_available:
        warnings.append("No enrichment source found. Price-only scans are blocked from final selection by data-quality gate.")
    if config.research_data_provider.startswith("finnhub") and not config.finnhub_api_key:
        warnings.append("Finnhub research provider is configured but VCB_ALT_FINNHUB_API_KEY is missing.")
    if config.intraday_data_provider == "alpaca" and not (config.alpaca_api_key and config.alpaca_api_secret):
        warnings.append("Alpaca intraday provider is configured but Alpaca credentials are missing.")
    if config.alpaca_api_key and config.alpaca_api_secret:
        warnings.append(
            "Alpaca credentials are configured but not live-verified by provider-status; "
            "run /api/provider-diagnostics/alpaca before production scans."
        )
    if config.data_provider == "stooq" and not config.stooq_api_key:
        warnings.append("Stooq may require an API key or captcha depending on access path.")
    return {
        "provider": provider,
        "configured_provider": config.data_provider,
        "external_api_enabled": config.external_api_enabled,
        "cache_ttl_hours": config.market_data_cache_ttl_hours,
        "timeout_seconds": config.market_data_timeout_seconds,
        "capabilities": capabilities,
        "scan_mode": config.scan_mode,
        "market_universe_provider": config.market_universe_provider,
        "market_universe_max_symbols": config.market_universe_max_symbols,
        "market_prefilter_limit": config.market_prefilter_limit,
        "market_snapshot_batch_size": config.market_snapshot_batch_size,
        "market_scan_requires_live_data": config.market_scan_requires_live_data,
        "market_universe_live_ready": bool(config.external_api_enabled and config.alpaca_api_key and config.alpaca_api_secret),
        "alpaca_diagnostics_endpoint": "/api/provider-diagnostics/alpaca",
        "provider_health_endpoint": "/api/provider-health",
        "provider_alerts_endpoint": "/api/admin/provider-alerts",
        "research_data_provider": config.research_data_provider,
        "research_capabilities": research_capabilities,
        "research_api_configured": bool(config.finnhub_api_key) if config.research_data_provider.startswith("finnhub") else False,
        "intraday_data_provider": config.intraday_data_provider,
        "intraday_api_configured": bool(config.alpaca_api_key and config.alpaca_api_secret),
        "intraday_capabilities": {
            "latest_quote": config.intraday_data_provider == "alpaca",
            "latest_trade": config.intraday_data_provider == "alpaca",
            "minute_bar": config.intraday_data_provider == "alpaca",
            "feed": config.alpaca_data_feed,
        },
        "sec_filings_enabled": config.sec_company_facts_enabled,
        "ai_summary_provider": config.ai_summary_provider,
        "summary_provider_label": "OpenAI explanation summary"
        if config.ai_summary_provider == "openai" and config.openai_api_key
        else "template summary",
        "summary_role": "explanation_only",
        "selection_source": "deterministic_scoring",
        "ai_summary_configured": config.ai_summary_provider == "template" or bool(config.openai_api_key),
        "enrichment_available": enrichment_available,
        "enrichment_path": "data/enrichment.csv",
        "warnings": warnings,
    }


def _operator_csv_path(config: AppConfig, filename: str) -> Path:
    """Resolve an operator-maintained CSV.

    These files used to be read only from root_dir/data while every cache resolves under
    VCB_ALT_DATA_DIR, so an operator who set DATA_DIR and put the file there got a silent
    fallback - no universe, or enrichment that never applied and left data coverage below
    the selection gate with no explanation. The default layout keeps both paths identical;
    the legacy location still works for existing installs.
    """
    preferred = config.data_dir / filename
    if preferred.exists():
        return preferred
    legacy = config.root_dir / "data" / filename
    return legacy if legacy.exists() else preferred


def manual_snapshot_path(config: AppConfig) -> Path:
    return _operator_csv_path(config, "snapshots.csv")


def enrichment_snapshot_path(config: AppConfig) -> Path:
    return _operator_csv_path(config, "enrichment.csv")


def get_manual_snapshot(config: AppConfig, ticker_value: str) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    snapshots = _load_manual_snapshots(str(manual_snapshot_path(config)))
    if ticker not in snapshots:
        raise NotFoundError(
            f"No manual snapshot found for {ticker}. Add it to data/snapshots.csv or use VCB_ALT_DATA_PROVIDER=sample."
        )
    return snapshots[ticker]


# Memoised for the life of the process and keyed only on the path, so a long-running
# server keeps serving the copy it read first. Editing snapshots.csv takes effect on
# the next restart; that is fine for an operator file that changes rarely, and it
# keeps a scan from re-reading the same CSV once per ticker.
@lru_cache(maxsize=8)
def _load_manual_snapshots(path_value: str) -> dict[str, StockSnapshot]:
    path = Path(path_value)
    if not path.exists():
        raise NotFoundError("Manual provider requires data/snapshots.csv. See data/snapshots.example.csv.")

    snapshots: dict[str, StockSnapshot] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError("Manual snapshot CSV has no header row.")
        unknown = set(reader.fieldnames) - SNAPSHOT_FIELDS
        if unknown:
            raise ValidationError(f"Manual snapshot CSV has unsupported columns: {', '.join(sorted(unknown))}")

        for line_number, row in enumerate(reader, start=2):
            snapshot = _row_to_snapshot(row, line_number)
            snapshots[snapshot.ticker] = snapshot
    if not snapshots:
        raise ValidationError("Manual snapshot CSV contains no rows.")
    return snapshots


def apply_research_enrichment(config: AppConfig, snapshot: StockSnapshot) -> StockSnapshot:
    enriched = snapshot
    if config.research_data_provider.startswith("finnhub") and config.finnhub_api_key:
        values = _load_finnhub_enrichment(config, snapshot.ticker)
        if values:
            enriched = _apply_enrichment_values(enriched, values, "finnhub")
    if config.research_data_provider in {"csv", "finnhub_csv"}:
        rows = _load_enrichment_rows(str(enrichment_snapshot_path(config)))
        values = rows.get(snapshot.ticker)
        if values:
            enriched = _apply_enrichment_values(enriched, values, str(values.get("enrichment_source") or "data/enrichment.csv"))
    return enriched


def apply_manual_enrichment(config: AppConfig, snapshot: StockSnapshot) -> StockSnapshot:
    return apply_research_enrichment(config, snapshot)


def apply_intraday_quote(config: AppConfig, snapshot: StockSnapshot) -> StockSnapshot:
    if config.intraday_data_provider != "alpaca":
        return snapshot
    if not config.alpaca_api_key or not config.alpaca_api_secret:
        return snapshot
    values = _load_alpaca_intraday(config, snapshot.ticker)
    source = snapshot.source
    if "+alpaca-intraday" not in source:
        source = f"{source}+alpaca-intraday"
    data_quality = snapshot.data_quality
    if "alpaca-intraday" not in data_quality:
        data_quality = f"{data_quality}+alpaca-intraday"
    return replace(snapshot, **values, source=source, data_quality=data_quality)


def _apply_enrichment_values(snapshot: StockSnapshot, values: dict[str, Any], source_label: str) -> StockSnapshot:
    merged = replace(snapshot, **values)
    source = snapshot.source
    suffix = source_label.replace("data/", "").replace(".csv", "").replace("/", "_")
    if suffix not in source:
        source = f"{source}+{suffix}"
    enrichment_source = str(values.get("enrichment_source") or source_label)
    enrichment_as_of = str(values.get("enrichment_as_of") or values.get("data_as_of") or snapshot.data_as_of)
    quality_suffix = source_label.replace("data/", "").replace(".csv", "")
    data_quality = snapshot.data_quality if quality_suffix in snapshot.data_quality else f"{snapshot.data_quality}+{quality_suffix}"
    return replace(
        merged,
        source=source,
        enrichment_source=enrichment_source,
        enrichment_as_of=enrichment_as_of,
        data_quality=data_quality,
    )


def _load_finnhub_enrichment(config: AppConfig, ticker: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    latest_date = date.today()
    from_30d = date.fromordinal(latest_date.toordinal() - 30).isoformat()
    from_90d = date.fromordinal(latest_date.toordinal() - 90).isoformat()
    from_180d = date.fromordinal(latest_date.toordinal() - 180).isoformat()
    to_date = latest_date.isoformat()

    metric = _finnhub_json(config, ticker, "metric", "/stock/metric", {"metric": "all"})
    values.update(_finnhub_metric_values(metric))

    earnings = _finnhub_json(config, ticker, "earnings", "/stock/earnings", {})
    values.update(_finnhub_earnings_values(earnings))

    news = _finnhub_json(config, ticker, "news", "/company-news", {"from": from_30d, "to": to_date})
    values.update(_finnhub_news_values(news))

    insider = _finnhub_json(config, ticker, "insider", "/stock/insider-transactions", {"from": from_90d, "to": to_date})
    values.update(_finnhub_insider_values(insider))

    short_interest = _finnhub_json(config, ticker, "short_interest", "/stock/short-interest", {"from": from_180d, "to": to_date})
    values.update(_finnhub_short_interest_values(short_interest))

    option_chain = _finnhub_json(config, ticker, "option_chain", "/stock/option-chain", {})
    values.update(_finnhub_option_values(option_chain))

    recommendation = _finnhub_json(config, ticker, "recommendation", "/stock/recommendation", {})
    values.update(_finnhub_recommendation_values(recommendation))

    if config.sec_company_facts_enabled:
        values.update(_load_sec_filing_values(config, ticker))

    if values:
        values["enrichment_source"] = "finnhub"
        values["enrichment_as_of"] = to_date
    return values


def _load_alpaca_intraday(config: AppConfig, ticker: str) -> dict[str, Any]:
    cache_path = _alpaca_intraday_cache_path(config.data_dir, ticker)
    cached = _read_fresh_cache_seconds(cache_path, config.intraday_cache_ttl_seconds)
    if cached is not None:
        try:
            return _alpaca_intraday_values(json.loads(cached), ticker)
        except (json.JSONDecodeError, AppError):
            cache_path.unlink(missing_ok=True)
    query = {"symbols": ticker, "feed": config.alpaca_data_feed}
    url = f"{ALPACA_DATA_BASE_URL}/v2/stocks/snapshots?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "APCA-API-KEY-ID": config.alpaca_api_key,
            "APCA-API-SECRET-KEY": config.alpaca_api_secret,
            "User-Agent": "vcb-alt-stock-screener/0.1",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        body = provider_request_text(config, "alpaca", request)
    except ProviderFailure as exc:
        return {"intraday_error": exc.message}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(body, encoding="utf-8")
    try:
        return _alpaca_intraday_values(json.loads(body), ticker)
    except (json.JSONDecodeError, AppError):
        return {"intraday_error": "Alpaca response could not be parsed."}


def _alpaca_intraday_values(payload: Any, ticker: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    snapshots = payload.get("snapshots") if isinstance(payload.get("snapshots"), dict) else payload
    snapshot = snapshots.get(ticker) or snapshots.get(ticker.upper()) if isinstance(snapshots, dict) else {}
    if not isinstance(snapshot, dict):
        return {}
    trade = snapshot.get("latestTrade") if isinstance(snapshot.get("latestTrade"), dict) else {}
    quote = snapshot.get("latestQuote") if isinstance(snapshot.get("latestQuote"), dict) else {}
    minute = snapshot.get("minuteBar") if isinstance(snapshot.get("minuteBar"), dict) else {}
    daily = snapshot.get("dailyBar") if isinstance(snapshot.get("dailyBar"), dict) else {}
    previous = snapshot.get("prevDailyBar") if isinstance(snapshot.get("prevDailyBar"), dict) else {}
    price = _first_number(trade, ["p", "price"])
    if not price:
        ask = _first_number(quote, ["ap", "askPrice"])
        bid = _first_number(quote, ["bp", "bidPrice"])
        price = (ask + bid) / 2 if ask and bid else ask or bid
    volume = _first_number(minute, ["v", "volume"]) or _first_number(daily, ["v", "volume"])
    previous_close = _first_number(previous, ["c", "close"])
    change_pct = ((price - previous_close) / previous_close) * 100 if price and previous_close else 0.0
    as_of = str(trade.get("t") or quote.get("t") or minute.get("t") or "")
    values: dict[str, Any] = {}
    if price:
        values["intraday_price"] = round(price, 4)
        values["intraday_change_pct"] = round(change_pct, 2)
        values["intraday_source"] = "alpaca"
        values["intraday_as_of"] = as_of
        values["intraday_freshness_seconds"] = _iso_age_seconds(as_of)
    if volume:
        values["intraday_volume"] = round(volume, 2)
    if not values:
        values["intraday_error"] = "Alpaca snapshot response did not include a latest trade, quote, or minute bar."
    return values


def _alpaca_http_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")[:240]
    except Exception:
        body = ""
    if exc.code in {401, 403}:
        return (
            f"Alpaca rejected the request with HTTP {exc.code}. "
            "Check that the Key ID/Secret are from the same account and that the selected data feed is allowed."
        )
    if exc.code == 429:
        return "Alpaca rate limit reached."
    return f"Alpaca request failed with HTTP {exc.code}. {body}".strip()


def _finnhub_json(config: AppConfig, ticker: str, cache_name: str, path: str, params: dict[str, str]) -> Any:
    cache_path = _finnhub_cache_path(config.data_dir, ticker, cache_name)
    cached = _read_fresh_cache(cache_path, config.research_data_cache_ttl_hours)
    if cached is not None:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)
    query = {"symbol": ticker, "token": config.finnhub_api_key, **params}
    url = f"{FINNHUB_BASE_URL}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "vcb-alt-stock-screener/0.1",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        payload = provider_request_json(config, "finnhub", request)
    except ProviderFailure:
        return {}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(body, encoding="utf-8")
    return payload


def _finnhub_cache_path(data_dir: Path, ticker: str, cache_name: str) -> Path:
    safe_name = ticker.lower().replace("/", "_").replace("\\", "_")
    return data_dir / "research_cache" / "finnhub" / RESEARCH_CACHE_VERSION / f"{safe_name}_{cache_name}.json"


def _alpaca_intraday_cache_path(data_dir: Path, ticker: str) -> Path:
    safe_name = ticker.lower().replace("/", "_").replace("\\", "_")
    return data_dir / "intraday_cache" / "alpaca" / INTRADAY_CACHE_VERSION / f"{safe_name}_snapshot.json"


def _sec_submissions_cache_path(data_dir: Path, cik: str) -> Path:
    return data_dir / "research_cache" / "sec" / SEC_CACHE_VERSION / "submissions" / f"{cik}.json"


def _finnhub_metric_values(payload: Any) -> dict[str, Any]:
    metric = payload.get("metric", {}) if isinstance(payload, dict) else {}
    values: dict[str, Any] = {}
    market_cap = _first_number(metric, ["marketCapitalization", "marketCap"])
    if market_cap:
        values["market_cap_m"] = market_cap
    shares = _first_number(metric, ["floatShares", "shareOutstanding"])
    if shares:
        values["float_shares_m"] = shares
    revenue_growth = _first_number(metric, ["revenueGrowthQuarterlyYoy", "revenueGrowthTTMYoy"])
    if revenue_growth:
        values["revenue_acceleration_pp"] = revenue_growth
    eps_growth = _first_number(metric, ["epsGrowthQuarterlyYoy", "epsGrowthTTMYoy"])
    if eps_growth:
        values["eps_revision_pct"] = eps_growth
    return values


def _finnhub_earnings_values(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    if not rows:
        return {}
    latest = rows[0] if isinstance(rows[0], dict) else {}
    surprise = _first_number(latest, ["surprisePercent"])
    if surprise == 0:
        actual = _first_number(latest, ["actual"])
        estimate = _first_number(latest, ["estimate"])
        if estimate:
            surprise = ((actual - estimate) / abs(estimate)) * 100
    if not surprise:
        return {}
    rounded = round(surprise, 2)
    return {"earnings_surprise_pct": rounded, "revenue_surprise_pct": rounded}


def _finnhub_news_values(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    text = " ".join(
        str(item.get("headline", "")) + " " + str(item.get("summary", ""))
        for item in rows
        if isinstance(item, dict)
    ).lower()
    catalyst_terms = ["contract", "partnership", "approval", "fda", "beats", "guidance", "launch", "acquisition"]
    values: dict[str, Any] = {}
    if rows:
        values["news_headline_count_30d"] = len(rows)
    if any(term in text for term in catalyst_terms):
        values["news_catalyst_30d"] = True
    if "data center" in text or "datacenter" in text or "ai infrastructure" in text:
        values["data_center_narrative"] = True
    if "raises guidance" in text or "raised guidance" in text:
        values["forward_guidance_raised"] = True
    return values


def _finnhub_insider_values(payload: Any) -> dict[str, Any]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    buys = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        code = str(item.get("transactionCode", "")).upper()
        shares = _first_number(item, ["share", "change", "transactionShares"])
        if code in {"P", "A"} and shares > 0:
            buys += 1
    return {"insider_buy_count_90d": buys} if buys else {}


def _finnhub_short_interest_values(payload: Any) -> dict[str, Any]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    latest = rows[0] if rows and isinstance(rows[0], dict) else {}
    values: dict[str, Any] = {}
    short_pct = _first_number(latest, ["shortPercent", "shortInterestPercentFloat", "shortInterestPercent"])
    if short_pct:
        values["short_interest_pct"] = short_pct
    days = _first_number(latest, ["daysToCover"])
    if days:
        values["days_to_cover"] = days
    return values


def _finnhub_option_values(payload: Any) -> dict[str, Any]:
    data = payload.get("data", []) if isinstance(payload, dict) else []
    call_oi = 0.0
    put_oi = 0.0
    for chain in data:
        if not isinstance(chain, dict):
            continue
        for row in chain.get("options", {}).get("CALL", []):
            if isinstance(row, dict):
                call_oi += _first_number(row, ["openInterest"])
        for row in chain.get("options", {}).get("PUT", []):
            if isinstance(row, dict):
                put_oi += _first_number(row, ["openInterest"])
    values: dict[str, Any] = {}
    if call_oi:
        values["call_open_interest"] = round(call_oi, 2)
    if put_oi:
        values["put_open_interest"] = round(put_oi, 2)
        values["put_call_ratio"] = round(put_oi / call_oi, 3) if call_oi else 0.0
    if call_oi and put_oi and call_oi >= put_oi * 2:
        values["call_oi_change_pct"] = 200.0
    return values


def _finnhub_recommendation_values(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    latest = rows[0] if rows and isinstance(rows[0], dict) else {}
    if not latest:
        return {}
    buy = int(_first_number(latest, ["strongBuy"]) + _first_number(latest, ["buy"]))
    hold = int(_first_number(latest, ["hold"]))
    sell = int(_first_number(latest, ["sell"]) + _first_number(latest, ["strongSell"]))
    total = buy + hold + sell
    if not total:
        return {}
    score = ((buy - sell) / total) * 100
    return {
        "analyst_revision_score": round(score, 2),
        "analyst_buy_count": buy,
        "analyst_hold_count": hold,
        "analyst_sell_count": sell,
    }


def _load_sec_filing_values(config: AppConfig, ticker: str) -> dict[str, Any]:
    cik = _lookup_sec_cik(config, ticker)
    if not cik:
        return {}
    cache_path = _sec_submissions_cache_path(config.data_dir, cik)
    cached = _read_fresh_cache(cache_path, config.research_data_cache_ttl_hours)
    if cached is not None:
        try:
            return _sec_filing_values(json.loads(cached), cik)
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)
    url = f"{SEC_SUBMISSIONS_BASE_URL}/CIK{cik}.json"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.sec_user_agent,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        payload = provider_request_json(config, "sec", request)
    except ProviderFailure:
        return {}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(body, encoding="utf-8")
    return _sec_filing_values(payload, cik)


def _lookup_sec_cik(config: AppConfig, ticker: str) -> str:
    cache_path = config.data_dir / "research_cache" / "sec" / SEC_CACHE_VERSION / "company_tickers.json"
    cached = _read_fresh_cache(cache_path, config.research_data_cache_ttl_hours)
    if cached is None:
        request = urllib.request.Request(
            SEC_TICKER_CIK_URL,
            headers={"User-Agent": config.sec_user_agent, "Accept": "application/json,text/plain,*/*"},
        )
        try:
            payload = provider_request_json(config, "sec", request)
            cached = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except ProviderFailure:
            return ""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(cached, encoding="utf-8")
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        return ""
    for item in payload.values() if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("ticker", "")).upper() == ticker.upper():
            raw_cik = str(item.get("cik_str", "")).strip()
            return raw_cik.zfill(10) if raw_cik else ""
    return ""


def _sec_filing_values(payload: Any, cik: str) -> dict[str, Any]:
    recent = payload.get("filings", {}).get("recent", {}) if isinstance(payload, dict) else {}
    forms = recent.get("form", []) if isinstance(recent, dict) else []
    filing_dates = recent.get("filingDate", []) if isinstance(recent, dict) else []
    accession_numbers = recent.get("accessionNumber", []) if isinstance(recent, dict) else []
    primary_docs = recent.get("primaryDocument", []) if isinstance(recent, dict) else []
    if not forms or not filing_dates:
        return {}
    important_forms = {"10-K", "10-Q", "8-K", "S-1", "424B", "DEF 14A", "SC 13D", "SC 13G"}
    best_index = 0
    for index, form in enumerate(forms):
        if str(form).upper() in important_forms:
            best_index = index
            break
    form = str(forms[best_index])
    filing_date = str(filing_dates[best_index])
    accession = str(accession_numbers[best_index]) if best_index < len(accession_numbers) else ""
    doc = str(primary_docs[best_index]) if best_index < len(primary_docs) else ""
    values = {
        "latest_filing_date": filing_date,
        "latest_filing_type": form,
        "filing_catalyst_30d": _date_within_days(filing_date, 30),
    }
    if accession and doc:
        clean_accession = accession.replace("-", "")
        values["latest_filing_url"] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{clean_accession}/{doc}"
    return values


def _first_number(mapping: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        raw = mapping.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def apply_csv_enrichment(config: AppConfig, snapshot: StockSnapshot) -> StockSnapshot:
    rows = _load_enrichment_rows(str(enrichment_snapshot_path(config)))
    values = rows.get(snapshot.ticker)
    if not values:
        return snapshot
    return _apply_enrichment_values(snapshot, values, str(values.get("enrichment_source") or "data/enrichment.csv"))


# Same trade-off as _load_manual_snapshots: cached per process, so an edited
# enrichment.csv needs a restart to be picked up.
@lru_cache(maxsize=8)
def _load_enrichment_rows(path_value: str) -> dict[str, dict[str, Any]]:
    path = Path(path_value)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError("Enrichment CSV has no header row.")
        unknown = set(reader.fieldnames) - (ENRICHMENT_FIELDS | {"ticker", "enrichment_source", "enrichment_as_of"})
        if unknown:
            raise ValidationError(f"Enrichment CSV has unsupported columns: {', '.join(sorted(unknown))}")
        rows: dict[str, dict[str, Any]] = {}
        for line_number, row in enumerate(reader, start=2):
            ticker = validate_ticker((row.get("ticker") or "").strip())
            values = _row_to_enrichment_values(row, line_number)
            rows[ticker] = values
    return rows


def _row_to_enrichment_values(row: dict[str, str | None], line_number: int) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in ENRICHMENT_FIELDS | {"enrichment_source", "enrichment_as_of"}:
        raw = (row.get(key) or "").strip()
        if raw == "":
            continue
        if key in TEXT_FIELDS:
            values[key] = raw
        elif key in BOOL_FIELDS:
            values[key] = _parse_bool(raw)
        elif key in INT_FIELDS:
            values[key] = _parse_int(raw, key, line_number)
        else:
            values[key] = _parse_float(raw, key, line_number)
    return values


def _row_to_snapshot(row: dict[str, str | None], line_number: int) -> StockSnapshot:
    values: dict[str, Any] = {}
    for key in SNAPSHOT_FIELDS:
        raw = (row.get(key) or "").strip()
        if key == "ticker":
            values[key] = validate_ticker(raw)
        elif key == "company_name":
            values[key] = raw or values.get("ticker", "Unknown")
        elif key in TEXT_FIELDS:
            values[key] = raw
        elif key in BOOL_FIELDS:
            values[key] = _parse_bool(raw)
        elif key in INT_FIELDS:
            values[key] = _parse_int(raw, key, line_number)
        else:
            values[key] = _parse_float(raw, key, line_number)
    values.setdefault("source", "manual")
    if not values.get("source"):
        values["source"] = "manual"
    if not values.get("data_as_of"):
        values["data_as_of"] = "manual-csv"
    return StockSnapshot(**values)


def _parse_float(raw: str, field_name: str, line_number: int) -> float:
    if raw == "":
        return 0.0
    try:
        return float(raw)
    except ValueError as exc:
        raise ValidationError(f"Line {line_number}: {field_name} must be a number.") from exc


def _parse_int(raw: str, field_name: str, line_number: int) -> int:
    if raw == "":
        return 0
    try:
        return int(float(raw))
    except ValueError as exc:
        raise ValidationError(f"Line {line_number}: {field_name} must be an integer.") from exc


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_stooq_snapshot(config: AppConfig, ticker_value: str) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    bars = _load_stooq_bars(
        str(config.data_dir),
        ticker,
        float(config.market_data_timeout_seconds),
        float(config.market_data_cache_ttl_hours),
        config.stooq_api_key,
    )
    benchmark_bars: list[MarketBar] | None = None
    if ticker != "SPY":
        try:
            benchmark_bars = _load_stooq_bars(
                str(config.data_dir),
                "SPY",
                float(config.market_data_timeout_seconds),
                float(config.market_data_cache_ttl_hours),
                config.stooq_api_key,
            )
        except AppError:
            benchmark_bars = None
    snapshot = build_snapshot_from_bars(ticker, bars, benchmark_bars, source="stooq")
    return apply_manual_enrichment(config, apply_intraday_quote(config, snapshot))


def get_yahoo_snapshot(config: AppConfig, ticker_value: str) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    bars, company_name = _load_yahoo_bars(
        str(config.data_dir),
        ticker,
        float(config.market_data_timeout_seconds),
        float(config.market_data_cache_ttl_hours),
        "1y",
        config,
    )
    benchmark_bars: list[MarketBar] | None = None
    if ticker != "SPY":
        try:
            benchmark_bars, _ = _load_yahoo_bars(
                str(config.data_dir),
                "SPY",
                float(config.market_data_timeout_seconds),
                float(config.market_data_cache_ttl_hours),
                "1y",
                config,
            )
        except AppError:
            benchmark_bars = None
    snapshot = build_snapshot_from_bars(ticker, bars, benchmark_bars, company_name=company_name, source="yahoo")
    return apply_manual_enrichment(config, apply_intraday_quote(config, snapshot))


def get_ticker_profile(config: AppConfig, ticker_value: str, *, snapshot: StockSnapshot | None = None) -> dict[str, Any]:
    ticker = validate_ticker(ticker_value)
    override = PROFILE_OVERRIDES.get(ticker, {})
    snapshot = snapshot or get_snapshot(config, ticker)
    return {
        "ticker": ticker,
        "company_name": snapshot.company_name,
        "sector": override.get("sector", "Unknown sector"),
        "industry": override.get("industry", "Unknown industry"),
        "profile_source": "curated-default" if override else "provider-unavailable",
    }


def get_price_history(config: AppConfig, ticker_value: str, years: int = 5) -> dict[str, Any]:
    ticker = validate_ticker(ticker_value)
    range_value = f"{max(1, min(years, 10))}y"
    # Public detail pages must label these daily bars as delayed/EOD until a licensed real-time feed is integrated.
    if config.data_provider in {"yahoo", "yahoo_chart"} and config.external_api_enabled:
        bars, _ = _load_yahoo_bars(
            str(config.data_dir),
            ticker,
            float(config.market_data_timeout_seconds),
            float(config.market_data_cache_ttl_hours),
            range_value,
            config,
        )
        return _history_payload(ticker, bars, "yahoo", range_value)
    if config.data_provider == "stooq" and config.external_api_enabled:
        bars = _load_stooq_bars(
            str(config.data_dir),
            ticker,
            float(config.market_data_timeout_seconds),
            float(config.market_data_cache_ttl_hours),
            config.stooq_api_key,
        )
        return _history_payload(ticker, bars[-(years * 252) :], "stooq", range_value)
    return _sample_history_payload(config, ticker, years)


def _history_payload(ticker: str, bars: list[MarketBar], source: str, range_value: str) -> dict[str, Any]:
    usable = sorted((bar for bar in bars if bar.close > 0), key=lambda item: item.date)
    if not usable:
        raise NotFoundError(f"No price history available for {ticker}.")
    return {
        "ticker": ticker,
        "source": source,
        "range": range_value,
        "interval": "1d",
        "freshness": _data_quality(usable, usable[-1].date),
        "is_realtime": False,
        "realtime_note": "Current provider supplies end-of-day/delayed chart data, not tick-by-tick real-time data.",
        "points": [
            {
                "date": bar.date.isoformat(),
                "open": round(bar.open, 4),
                "high": round(bar.high, 4),
                "low": round(bar.low, 4),
                "close": round(bar.close, 4),
                "volume": round(bar.volume, 2),
            }
            for bar in usable
        ],
    }


def _sample_history_payload(config: AppConfig, ticker: str, years: int) -> dict[str, Any]:
    snapshot = get_snapshot(config, ticker)
    end = date.today()
    total = max(260, years * 252)
    start_price = max(1.0, snapshot.price * 0.55)
    bars: list[MarketBar] = []
    for index in range(total):
        progress = index / max(1, total - 1)
        close = start_price + (snapshot.price - start_price) * progress
        volume = max(100_000.0, 1_000_000.0 + (index % 21) * 25_000.0)
        current_date = end.fromordinal(end.toordinal() - (total - index))
        bars.append(MarketBar(current_date, close * 0.995, close * 1.01, close * 0.99, close, volume))
    return _history_payload(ticker, bars, snapshot.source, f"{years}y")


def build_snapshot_from_bars(
    ticker_value: str,
    bars: list[MarketBar],
    benchmark_bars: list[MarketBar] | None = None,
    *,
    company_name: str | None = None,
    source: str = "market",
) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    cleaned = sorted((bar for bar in bars if bar.close > 0), key=lambda item: item.date)
    if not cleaned:
        raise NotFoundError(f"No market data rows were available for {ticker}.")
    latest = cleaned[-1]
    closes = [bar.close for bar in cleaned]
    highs = [bar.high for bar in cleaned]
    lows = [bar.low for bar in cleaned]
    volumes = [bar.volume for bar in cleaned]

    latest_close = latest.close
    sma_50 = _sma(closes, 50)
    sma_150 = _sma(closes, 150)
    sma_200 = _sma(closes, 200)
    prior_sma_200 = _sma(closes[:-21], 200) if len(closes) >= 221 else None
    high_52w = max(highs[-252:]) if highs else latest.high
    low_52w = min(lows[-252:]) if lows else latest.low
    avg_volume_50 = _mean(volumes[-51:-1]) if len(volumes) >= 51 else _mean(volumes[:-1])
    volume_ratio = latest.volume / avg_volume_50 if avg_volume_50 and avg_volume_50 > 0 else 1.0
    volume_z = _z_score(volumes[-30:], latest.volume)
    return_12w = _return_pct(closes, 63)
    return_12m = _return_pct(closes, 252)
    benchmark_return_12w = _return_pct([bar.close for bar in sorted(benchmark_bars or [], key=lambda item: item.date)], 63)
    sector_rs = return_12w - benchmark_return_12w if benchmark_return_12w else 0.0
    drawdown_52w = ((latest_close - high_52w) / high_52w) * 100 if high_52w > 0 else 0.0
    drawdown_recovery = ((latest_close - low_52w) / low_52w) * 100 if low_52w > 0 else 0.0
    price_vs_50 = _distance_pct(latest_close, sma_50)
    price_vs_150 = _distance_pct(latest_close, sma_150)
    price_vs_200 = _distance_pct(latest_close, sma_200)
    trend_score = _trend_template_score(latest_close, sma_50, sma_150, sma_200, prior_sma_200, high_52w, low_52w)
    surge_score = _surge_score(return_12w, volume_ratio, volume_z, drawdown_recovery, price_vs_200)
    rr_ratio = _risk_reward_ratio(latest_close, high_52w)
    data_quality = _data_quality(cleaned, latest.date)

    return StockSnapshot(
        ticker=ticker,
        company_name=company_name or f"{ticker} market data",
        price=round(latest_close, 4),
        sector_rs_12w_pp=round(sector_rs, 2),
        breakout_volume_ratio=round(volume_ratio, 2),
        drawdown_recovery_pct=round(drawdown_recovery, 2),
        above_200dma=bool(sma_200 and latest_close > sma_200),
        volume_z_score_30d=round(volume_z, 2),
        source=source,
        data_as_of=latest.date.isoformat(),
        data_quality=data_quality,
        return_12w_pct=round(return_12w, 2),
        return_12m_pct=round(return_12m, 2),
        drawdown_52w_pct=round(drawdown_52w, 2),
        price_vs_50dma_pct=round(price_vs_50, 2),
        price_vs_150dma_pct=round(price_vs_150, 2),
        price_vs_200dma_pct=round(price_vs_200, 2),
        trend_template_score=trend_score,
        surge_score=surge_score,
        rr_ratio=round(rr_ratio, 2),
    )


def _load_stooq_bars(
    data_dir_value: str,
    ticker: str,
    timeout_seconds: float,
    cache_ttl_hours: float,
    api_key: str,
) -> list[MarketBar]:
    return _load_stooq_bars_cached(
        data_dir_value,
        ticker,
        timeout_seconds,
        cache_ttl_hours,
        api_key,
        _ttl_bucket(cache_ttl_hours),
    )


@lru_cache(maxsize=1024)
def _load_stooq_bars_cached(
    data_dir_value: str,
    ticker: str,
    timeout_seconds: float,
    cache_ttl_hours: float,
    api_key: str,
    ttl_bucket: int,
) -> list[MarketBar]:
    del ttl_bucket
    cache_path = _stooq_cache_path(Path(data_dir_value), ticker)
    csv_text = _read_fresh_cache(cache_path, cache_ttl_hours)
    if csv_text is not None:
        try:
            return _parse_stooq_csv(csv_text, ticker)
        except AppError:
            cache_path.unlink(missing_ok=True)
    csv_text = _fetch_stooq_csv(ticker, timeout_seconds, api_key)
    bars = _parse_stooq_csv(csv_text, ticker)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(csv_text, encoding="utf-8")
    return bars


def _load_yahoo_bars(
    data_dir_value: str,
    ticker: str,
    timeout_seconds: float,
    cache_ttl_hours: float,
    range_value: str = "1y",
    config: AppConfig | None = None,
) -> tuple[list[MarketBar], str | None]:
    """Load daily bars, preferring the on-disk cache over a network fetch.

    There used to be a second, process-memoised copy of this for callers without a
    config. Every caller passes one, so that copy only ever ran from its own test while
    the real path stayed uncached. Re-parsing a cached file measures at under a
    millisecond against a network fetch of roughly a second, so one uncached
    implementation is both simpler and fast enough.
    """
    cache_path = _yahoo_cache_path(Path(data_dir_value), ticker, range_value)
    json_text = _read_fresh_cache(cache_path, cache_ttl_hours)
    if json_text is not None:
        try:
            return _parse_yahoo_chart_json(json_text, ticker)
        except AppError:
            cache_path.unlink(missing_ok=True)
    json_text = _fetch_yahoo_chart_json(ticker, timeout_seconds, range_value, config)
    parsed = _parse_yahoo_chart_json(json_text, ticker)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json_text, encoding="utf-8")
    return parsed


def _ttl_bucket(cache_ttl_hours: float) -> int:
    return int(time.time() // max(1.0, cache_ttl_hours * 3600))


def _yahoo_cache_path(data_dir: Path, ticker: str, range_value: str = "1y") -> Path:
    safe_name = ticker.lower().replace("/", "_").replace("\\", "_")
    suffix = "" if range_value == "1y" else f"_{range_value}"
    return data_dir / "market_cache" / "yahoo" / STOOQ_CACHE_VERSION / f"{safe_name}{suffix}.json"


def _fetch_yahoo_chart_json(
    ticker: str,
    timeout_seconds: float,
    range_value: str = "1y",
    config: AppConfig | None = None,
) -> str:
    encoded_ticker = urllib.parse.quote(validate_ticker(ticker), safe="")
    url = f"{YAHOO_CHART_BASE_URL}/{encoded_ticker}?{urllib.parse.urlencode({'range': range_value, 'interval': '1d'})}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "vcb-alt-stock-screener/0.1",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    if config is not None:
        try:
            return provider_request_text(config, "yahoo", request, timeout_seconds=timeout_seconds)
        except ProviderFailure as exc:
            raise NotFoundError(
                f"Could not fetch Yahoo chart data for {ticker}. {exc.message}",
                detail=exc.recovery,
            ) from exc
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise NotFoundError(
            f"Could not fetch Yahoo chart data for {ticker}. Check network access or use VCB_ALT_DATA_PROVIDER=sample.",
            detail=str(exc.reason),
        ) from exc
    except TimeoutError as exc:
        raise NotFoundError(f"Yahoo chart data fetch timed out for {ticker}.") from exc


def _parse_yahoo_chart_json(json_text: str, ticker: str) -> tuple[list[MarketBar], str | None]:
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise NotFoundError(f"Invalid Yahoo chart response for {ticker}.") from exc
    chart = payload.get("chart") if isinstance(payload, dict) else None
    if not isinstance(chart, dict) or chart.get("error"):
        raise NotFoundError(f"Yahoo chart returned an error for {ticker}.")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise NotFoundError(f"No Yahoo chart data found for {ticker}.")
    result = results[0]
    if not isinstance(result, dict):
        raise NotFoundError(f"Invalid Yahoo chart payload for {ticker}.")
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    timestamps = result.get("timestamp")
    indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    if not isinstance(timestamps, list) or not isinstance(quotes, list) or not quotes:
        raise NotFoundError(f"Incomplete Yahoo chart data for {ticker}.")
    quote = quotes[0]
    if not isinstance(quote, dict):
        raise NotFoundError(f"Invalid Yahoo quote payload for {ticker}.")
    bars = _bars_from_yahoo_arrays(timestamps, quote, ticker)
    company_name = meta.get("longName") or meta.get("shortName") or meta.get("symbol")
    return bars, str(company_name) if company_name else None


def _bars_from_yahoo_arrays(timestamps: list[Any], quote: dict[str, Any], ticker: str) -> list[MarketBar]:
    opens = quote.get("open")
    highs = quote.get("high")
    lows = quote.get("low")
    closes = quote.get("close")
    volumes = quote.get("volume")
    if not all(isinstance(values, list) for values in (opens, highs, lows, closes, volumes)):
        raise NotFoundError(f"Incomplete Yahoo OHLCV arrays for {ticker}.")
    bars: list[MarketBar] = []
    for index, timestamp in enumerate(timestamps):
        try:
            raw_values = (opens[index], highs[index], lows[index], closes[index], volumes[index])
        except IndexError as exc:
            raise NotFoundError(f"Misaligned Yahoo OHLCV arrays for {ticker}.") from exc
        if any(value is None for value in raw_values):
            continue
        try:
            bars.append(
                MarketBar(
                    date=datetime.fromtimestamp(float(timestamp), timezone.utc).date(),
                    open=float(raw_values[0]),
                    high=float(raw_values[1]),
                    low=float(raw_values[2]),
                    close=float(raw_values[3]),
                    volume=float(raw_values[4]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid Yahoo chart row for {ticker}.") from exc
    if not bars:
        raise NotFoundError(f"No usable Yahoo chart rows found for {ticker}.")
    return bars


def _stooq_cache_path(data_dir: Path, ticker: str) -> Path:
    safe_name = ticker.lower().replace("/", "_").replace("\\", "_")
    return data_dir / "market_cache" / "stooq" / STOOQ_CACHE_VERSION / f"{safe_name}.csv"


def _read_fresh_cache(path: Path, ttl_hours: float) -> str | None:
    if not path.exists():
        return None
    max_age_seconds = ttl_hours * 3600
    if time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    return path.read_text(encoding="utf-8")


def _read_fresh_cache_seconds(path: Path, ttl_seconds: float) -> str | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl_seconds:
        return None
    return path.read_text(encoding="utf-8")


def _iso_age_seconds(value: str) -> float:
    if not value:
        return 0.0
    try:
        normalized = value.replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())


def _date_within_days(value: str, days: int) -> bool:
    try:
        filing_date = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return False
    delta_days = (datetime.now(timezone.utc).date() - filing_date).days
    return -1 <= delta_days <= days


def _fetch_stooq_csv(ticker: str, timeout_seconds: float, api_key: str) -> str:
    symbol = _stooq_symbol(ticker)
    query = {"s": symbol, "i": "d"}
    if api_key:
        query["apikey"] = api_key
    url = f"{STOOQ_BASE_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "vcb-alt-stock-screener/0.1 (+https://example.invalid)",
            "Accept": "text/csv,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8-sig")
    except urllib.error.URLError as exc:
        raise NotFoundError(
            f"Could not fetch market data for {ticker}. Check network access or use VCB_ALT_DATA_PROVIDER=sample.",
            detail=str(exc.reason),
        ) from exc
    except TimeoutError as exc:
        raise NotFoundError(f"Market data fetch timed out for {ticker}.") from exc


def _stooq_symbol(ticker: str) -> str:
    normalized = validate_ticker(ticker).lower()
    if normalized.startswith("^") or normalized.endswith(".us"):
        return normalized
    return f"{normalized}.us"


def _parse_stooq_csv(csv_text: str, ticker: str) -> list[MarketBar]:
    sample = csv_text.strip()
    if not sample or sample.lower().startswith("no data"):
        raise NotFoundError(f"No Stooq market data found for {ticker}.")
    if sample.lower().startswith("get your apikey"):
        raise NotFoundError(
            "Stooq CSV download requires an API key/captcha for this symbol. "
            "Use VCB_ALT_DATA_PROVIDER=yahoo or configure VCB_ALT_STOOQ_API_KEY."
        )
    reader = csv.DictReader(sample.splitlines())
    if not reader.fieldnames:
        raise NotFoundError(f"No Stooq CSV header found for {ticker}.")
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(reader.fieldnames)):
        raise NotFoundError(f"Unexpected Stooq CSV format for {ticker}.")
    bars: list[MarketBar] = []
    for row in reader:
        try:
            bars.append(
                MarketBar(
                    date=datetime.strptime(str(row["Date"]), "%Y-%m-%d").date(),
                    open=float(str(row["Open"])),
                    high=float(str(row["High"])),
                    low=float(str(row["Low"])),
                    close=float(str(row["Close"])),
                    volume=float(str(row["Volume"])),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid Stooq CSV row for {ticker}.") from exc
    if not bars:
        raise NotFoundError(f"No Stooq market data rows found for {ticker}.")
    return bars


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return _mean(values[-window:])


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _return_pct(values: list[float], lookback: int) -> float:
    if len(values) <= lookback:
        return 0.0
    previous = values[-lookback - 1]
    current = values[-1]
    if previous <= 0:
        return 0.0
    return ((current - previous) / previous) * 100


def _distance_pct(current: float, base: float | None) -> float:
    if not base or base <= 0:
        return 0.0
    return ((current - base) / base) * 100


def _z_score(values: list[float], latest: float) -> float:
    if len(values) < 3:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    stddev = math.sqrt(variance)
    if stddev == 0:
        return 0.0
    return (latest - mean) / stddev


def _trend_template_score(
    close: float,
    sma_50: float | None,
    sma_150: float | None,
    sma_200: float | None,
    prior_sma_200: float | None,
    high_52w: float,
    low_52w: float,
) -> int:
    score = 0
    score += 12 if sma_50 and close > sma_50 else 0
    score += 12 if sma_150 and close > sma_150 else 0
    score += 12 if sma_200 and close > sma_200 else 0
    score += 12 if sma_50 and sma_150 and sma_50 > sma_150 else 0
    score += 12 if sma_150 and sma_200 and sma_150 > sma_200 else 0
    score += 12 if sma_200 and prior_sma_200 and sma_200 > prior_sma_200 else 0
    score += 14 if low_52w > 0 and close >= low_52w * 1.30 else 0
    score += 14 if high_52w > 0 and close >= high_52w * 0.75 else 0
    return min(100, score)


def _surge_score(
    return_12w: float,
    volume_ratio: float,
    volume_z: float,
    drawdown_recovery: float,
    price_vs_200: float,
) -> int:
    score = 0
    score += 25 if volume_ratio >= 1.5 else 0
    score += 20 if volume_z >= 2 else 0
    score += 20 if return_12w >= 20 else 0
    score += 20 if drawdown_recovery >= 30 else 0
    score += 15 if price_vs_200 > 0 else 0
    return min(100, score)


def _risk_reward_ratio(close: float, high_52w: float) -> float:
    risk = close * 0.08
    reward = max(0.0, high_52w - close)
    if risk <= 0:
        return 0.0
    return reward / risk


def _data_quality(bars: list[MarketBar], latest_date: date) -> str:
    age_days = (datetime.now(timezone.utc).date() - latest_date).days
    if len(bars) < 80:
        return "thin-eod-market"
    if age_days > 10:
        return "stale-eod-market"
    if len(bars) < 200:
        return "partial-eod-market"
    return "eod-market"

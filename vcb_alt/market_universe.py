from __future__ import annotations

import csv
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .errors import AppError, ValidationError
from .models import EvaluationResult, PortfolioSelection, StockSnapshot
from .portfolio import select_portfolio
from .provider_resilience import ProviderFailure, provider_request_json, provider_request_text
from .providers import apply_research_enrichment, get_snapshot
from .sample_data import SAMPLE_TICKERS
from .scoring import evaluate_snapshot
from .validation import validate_ticker

ALPACA_TRADING_BASE_URLS = ("https://paper-api.alpaca.markets", "https://api.alpaca.markets")
ALPACA_TRADING_CONTEXTS = (
    ("paper", "https://paper-api.alpaca.markets"),
    ("live", "https://api.alpaca.markets"),
)
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
UNIVERSE_CACHE_VERSION = "v2"
LIVE_DATA_REQUIRED_MESSAGE = (
    "Fail-closed: live Alpaca market data is required for production market-wide research candidates. "
    "Sample/demo fallback is disabled; configure Alpaca assets and stock snapshots, or set "
    "VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=false only for local/demo mode."
)


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    name: str
    exchange: str
    source: str
    tradable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrefilterCandidate:
    ticker: str
    company_name: str
    exchange: str
    latest_price: float
    previous_close: float
    intraday_change_pct: float
    intraday_volume: float
    breakout_volume_ratio: float
    spread_bps: float
    prefilter_score: int
    source: str
    data_as_of: str
    freshness_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketScanResult:
    evaluations: list[EvaluationResult]
    failures: list[dict[str, Any]]
    selection: PortfolioSelection
    elapsed_ms: int
    universe: dict[str, Any]
    prefilter: dict[str, Any]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "scan_mode": "market_universe",
            "items": [item.to_dict() for item in self.evaluations],
            "failures": self.failures,
            "count": len(self.evaluations),
            "elapsed_ms": self.elapsed_ms,
            "selection": self.selection.to_dict(),
            "universe": self.universe,
            "prefilter": self.prefilter,
        }


def market_universe_path(root_dir: Path) -> Path:
    return root_dir / "data" / "universe.csv"


def scan_market_universe(
    config: AppConfig,
    *,
    universe_limit: int | None = None,
    prefilter_limit: int | None = None,
    max_positions: int = 3,
) -> MarketScanResult:
    cache_path = _market_scan_report_cache_path(config, universe_limit, prefilter_limit, max_positions)
    cached = _read_fresh_cache(cache_path, config.intraday_cache_ttl_seconds)
    if cached is not None:
        try:
            cached_result = _market_scan_result_from_json(cached)
            if config.market_scan_requires_live_data and not market_scan_report_has_live_data(cached_result):
                cache_path.unlink(missing_ok=True)
            else:
                cached_result.prefilter["cache"] = "hit"
                return cached_result
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            cache_path.unlink(missing_ok=True)
        except ValidationError:
            cache_path.unlink(missing_ok=True)
            raise

    start = time.perf_counter()
    limit = min(universe_limit or config.market_universe_max_symbols, config.market_universe_max_symbols)
    entries, universe_meta = load_market_universe(config, limit=limit)
    candidates, prefilter_meta = prefilter_market_candidates(config, entries, limit=prefilter_limit)
    failures: list[dict[str, Any]] = []

    if candidates:
        evaluations = _evaluate_prefiltered_candidates(config, candidates, failures)
    else:
        if config.market_scan_requires_live_data:
            raise live_data_required_error("No usable Alpaca snapshot candidates were returned.")
        evaluations = _evaluate_sample_universe(config, failures, limit=prefilter_limit or config.market_prefilter_limit)
        prefilter_meta["fallback"] = "sample_universe"

    selection = select_portfolio(evaluations, max_positions=max_positions)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    result = MarketScanResult(
        evaluations=evaluations,
        failures=failures,
        selection=selection,
        elapsed_ms=elapsed_ms,
        universe=universe_meta,
        prefilter=prefilter_meta,
    )
    if config.market_scan_requires_live_data:
        ensure_live_market_scan_report(config, result)
    result.prefilter["cache"] = "miss"
    _write_market_scan_report_cache(cache_path, result)
    return result


def live_data_required_error(reason: str | None = None) -> ValidationError:
    message = LIVE_DATA_REQUIRED_MESSAGE
    if reason:
        message = f"{message} Reason: {reason}"
    return ValidationError(message)


def ensure_live_market_scan_report(
    config: AppConfig,
    report: MarketScanResult | dict[str, Any],
    *,
    source: str = "market scan report",
) -> None:
    if not config.market_scan_requires_live_data:
        return
    if not market_scan_report_has_live_data(report):
        raise live_data_required_error(f"{source} is not backed by Alpaca stock snapshots.")


def market_scan_report_has_live_data(report: MarketScanResult | dict[str, Any]) -> bool:
    data = report.to_api_dict() if isinstance(report, MarketScanResult) else report
    if not isinstance(data, dict):
        return False
    universe = data.get("universe") if isinstance(data.get("universe"), dict) else {}
    prefilter = data.get("prefilter") if isinstance(data.get("prefilter"), dict) else {}
    if str(universe.get("source") or "").lower() == "sample":
        return False
    if str(prefilter.get("fallback") or "").lower() == "sample_universe":
        return False
    if not str(prefilter.get("source") or "").startswith("alpaca:"):
        return False
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return False
    return all(isinstance(item, dict) and str(item.get("source") or "").startswith("alpaca:") for item in items)


def load_market_universe(config: AppConfig, *, limit: int | None = None) -> tuple[list[UniverseEntry], dict[str, Any]]:
    warnings: list[str] = []
    source = config.market_universe_provider
    entries: list[UniverseEntry] = []

    if source in {"auto", "alpaca"} and _alpaca_configured(config):
        try:
            entries = _load_alpaca_assets(config)
            source = "alpaca"
        except AppError as exc:
            warnings.append(exc.message)
            if config.market_scan_requires_live_data or config.market_universe_provider == "alpaca":
                raise

    if not entries and source in {"auto", "csv"}:
        entries = _load_csv_universe(config)
        if entries:
            source = "csv"

    if not entries:
        if config.market_scan_requires_live_data:
            raise live_data_required_error("No Alpaca asset universe or operator CSV universe is available.")
        entries = [
            UniverseEntry(ticker=validate_ticker(ticker), name=validate_ticker(ticker), exchange="sample", source="sample")
            for ticker in SAMPLE_TICKERS
        ]
        source = "sample"
        warnings.append("Using sample universe because live Alpaca assets or data/universe.csv were not available.")

    entries = _dedupe_entries(entries)
    if limit is not None:
        entries = entries[: max(0, limit)]
    return entries, {
        "source": source,
        "count": len(entries),
        "max_symbols": config.market_universe_max_symbols,
        "warnings": warnings,
    }


def prefilter_market_candidates(
    config: AppConfig,
    entries: list[UniverseEntry],
    *,
    limit: int | None = None,
) -> tuple[list[PrefilterCandidate], dict[str, Any]]:
    selected_limit = limit or config.market_prefilter_limit
    if not entries:
        return [], {"source": "none", "count": 0, "warnings": ["Universe is empty."]}
    if not _alpaca_configured(config):
        return [], {
            "source": "unavailable",
            "count": 0,
            "warnings": ["Alpaca credentials/external API access are required for real-time market prefiltering."],
        }

    candidates: list[PrefilterCandidate] = []
    failures: list[dict[str, Any]] = []
    batch_size = max(1, min(config.market_snapshot_batch_size, 500))
    for offset in range(0, len(entries), batch_size):
        batch = entries[offset : offset + batch_size]
        try:
            payload = _load_alpaca_snapshot_batch(config, [entry.ticker for entry in batch])
        except ProviderFailure as exc:
            failures.append({"offset": offset, "code": exc.code, "message": exc.message, "recovery": exc.recovery})
            if config.market_scan_requires_live_data:
                raise
            continue
        except AppError as exc:
            failures.append({"offset": offset, "code": exc.code, "message": exc.message})
            continue
        snapshots = payload.get("snapshots") if isinstance(payload.get("snapshots"), dict) else payload
        if not isinstance(snapshots, dict):
            continue
        entry_by_symbol = {entry.ticker: entry for entry in batch}
        for symbol, raw_snapshot in snapshots.items():
            ticker = validate_ticker(str(symbol))
            entry = entry_by_symbol.get(ticker)
            if entry is None or not isinstance(raw_snapshot, dict):
                continue
            candidate = _candidate_from_alpaca_snapshot(config, entry, raw_snapshot)
            if candidate is not None:
                candidates.append(candidate)

    candidates.sort(key=_prefilter_sort_key)
    candidates = candidates[:selected_limit]
    return candidates, {
        "source": f"alpaca:{config.alpaca_data_feed}",
        "count": len(candidates),
        "scanned_symbols": len(entries),
        "prefilter_limit": selected_limit,
        "batch_size": batch_size,
        "failures": failures[:10],
        "warnings": [] if candidates else ["No usable Alpaca snapshots were returned for the universe."],
    }


def diagnose_alpaca_credentials(config: AppConfig, *, symbol: str = "AAPL") -> dict[str, Any]:
    ticker = validate_ticker(symbol)
    expected_vars = [
        "VCB_ALT_EXTERNAL_API_ENABLED",
        "VCB_ALT_ALPACA_API_KEY",
        "VCB_ALT_ALPACA_API_SECRET",
        "VCB_ALT_ALPACA_DATA_FEED",
    ]
    env_status = {
        "external_api_enabled": config.external_api_enabled,
        "key_configured": bool(config.alpaca_api_key),
        "secret_configured": bool(config.alpaca_api_secret),
        "feed": config.alpaca_data_feed,
        "expected_vercel_variables": expected_vars,
        "accepted_local_aliases": [name.removeprefix("VCB_ALT_") for name in expected_vars],
    }
    result: dict[str, Any] = {
        "provider": "alpaca",
        "ready": False,
        "classification": "missing_config",
        "environment": env_status,
        "trading": {},
        "market_data": {},
        "next_actions": [],
    }
    if not config.external_api_enabled:
        result["next_actions"].append("Set VCB_ALT_EXTERNAL_API_ENABLED=true before running live diagnostics.")
    if not config.alpaca_api_key:
        result["next_actions"].append("Set VCB_ALT_ALPACA_API_KEY to the Alpaca Key ID.")
    if not config.alpaca_api_secret:
        result["next_actions"].append("Set VCB_ALT_ALPACA_API_SECRET to the matching Alpaca Secret Key.")
    if result["next_actions"]:
        return result

    trading: dict[str, Any] = {}
    for context, base_url in ALPACA_TRADING_CONTEXTS:
        trading[context] = _probe_alpaca_endpoint(config, f"{base_url}/v2/account")
    market_data = _probe_alpaca_endpoint(
        config,
        f"{ALPACA_DATA_BASE_URL}/v2/stocks/snapshots?"
        + urllib.parse.urlencode({"symbols": ticker, "feed": config.alpaca_data_feed}),
    )
    result["trading"] = trading
    result["market_data"] = {"snapshot": market_data, "test_symbol": ticker, "feed": config.alpaca_data_feed}

    trading_ready = any(item.get("ok") for item in trading.values())
    market_ready = bool(market_data.get("ok"))
    result["ready"] = trading_ready and market_ready
    result["classification"] = _alpaca_diagnostic_classification(trading, market_data)
    result["next_actions"] = _alpaca_diagnostic_next_actions(result["classification"], config.alpaca_data_feed)
    return result


def _evaluate_prefiltered_candidates(
    config: AppConfig,
    candidates: list[PrefilterCandidate],
    failures: list[dict[str, Any]],
) -> list[EvaluationResult]:
    evaluations: list[EvaluationResult] = []
    for candidate in candidates:
        try:
            snapshot = _snapshot_from_prefilter(candidate)
            snapshot = apply_research_enrichment(config, snapshot)
            evaluations.append(evaluate_snapshot(snapshot))
        except AppError as exc:
            failures.append({"ticker": candidate.ticker, "code": exc.code, "message": exc.message})
    return evaluations


def _evaluate_sample_universe(config: AppConfig, failures: list[dict[str, Any]], *, limit: int) -> list[EvaluationResult]:
    evaluations: list[EvaluationResult] = []
    for ticker in list(SAMPLE_TICKERS)[: max(0, limit)]:
        try:
            evaluations.append(evaluate_snapshot(get_snapshot(config, ticker)))
        except AppError as exc:
            failures.append({"ticker": ticker, "code": exc.code, "message": exc.message})
    return evaluations


def _load_alpaca_assets(config: AppConfig) -> list[UniverseEntry]:
    cache_path = config.data_dir / "market_universe" / "alpaca" / UNIVERSE_CACHE_VERSION / "assets.json"
    body = _read_fresh_cache(cache_path, config.market_data_cache_ttl_hours * 3600)
    if body is None:
        query = urllib.parse.urlencode({"status": "active", "asset_class": "us_equity"})
        body = _request_alpaca_assets(config, query)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(body, encoding="utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        cache_path.unlink(missing_ok=True)
        raise ValidationError("Alpaca assets response could not be parsed.") from exc

    entries: list[UniverseEntry] = []
    if not isinstance(payload, list):
        return entries
    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "")).lower() != "active":
            continue
        if item.get("tradable") is False:
            continue
        symbol = str(item.get("symbol") or "")
        try:
            ticker = validate_ticker(symbol)
        except AppError:
            continue
        entries.append(
            UniverseEntry(
                ticker=ticker,
                name=str(item.get("name") or ticker),
                exchange=str(item.get("exchange") or ""),
                source="alpaca-assets",
                tradable=bool(item.get("tradable", True)),
            )
        )
    return entries


def _request_alpaca_assets(config: AppConfig, query: str) -> str:
    last_error: Exception | None = None
    for base_url in ALPACA_TRADING_BASE_URLS:
        request = urllib.request.Request(
            f"{base_url}/v2/assets?{query}",
            headers=_alpaca_headers(config),
        )
        try:
            return provider_request_text(config, "alpaca", request)
        except ProviderFailure as exc:
            last_error = exc
            if exc.status_code in {401, 403}:
                continue
            raise exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            continue
    if isinstance(last_error, ProviderFailure):
        raise last_error
    if isinstance(last_error, urllib.error.HTTPError):
        raise ValidationError(_alpaca_error_message(last_error)) from last_error
    raise ValidationError(f"Alpaca assets request failed: {last_error}")


def _load_csv_universe(config: AppConfig) -> list[UniverseEntry]:
    path = market_universe_path(config.root_dir)
    if not path.exists():
        return []
    entries: list[UniverseEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                ticker = validate_ticker(str(row.get("ticker") or row.get("symbol") or ""))
            except AppError:
                continue
            entries.append(
                UniverseEntry(
                    ticker=ticker,
                    name=str(row.get("name") or row.get("company_name") or ticker),
                    exchange=str(row.get("exchange") or "csv"),
                    source="data/universe.csv",
                    tradable=str(row.get("tradable", "true")).strip().lower() not in {"0", "false", "no"},
                )
            )
    return [entry for entry in entries if entry.tradable]


def _load_alpaca_snapshot_batch(config: AppConfig, symbols: list[str]) -> dict[str, Any]:
    safe_symbols = [validate_ticker(symbol) for symbol in symbols]
    key = hashlib.sha256((",".join(safe_symbols) + f":{config.alpaca_data_feed}").encode("utf-8")).hexdigest()[:24]
    cache_path = config.data_dir / "market_universe" / "alpaca" / UNIVERSE_CACHE_VERSION / "snapshots" / f"{key}.json"
    body = _read_fresh_cache(cache_path, config.intraday_cache_ttl_seconds)
    if body is None:
        query = urllib.parse.urlencode({"symbols": ",".join(safe_symbols), "feed": config.alpaca_data_feed})
        request = urllib.request.Request(
            f"{ALPACA_DATA_BASE_URL}/v2/stocks/snapshots?{query}",
            headers=_alpaca_headers(config),
        )
        payload = provider_request_json(config, "alpaca", request)
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(body, encoding="utf-8")
        return payload
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        cache_path.unlink(missing_ok=True)
        raise ValidationError("Alpaca snapshot response could not be parsed.") from exc


def _candidate_from_alpaca_snapshot(
    config: AppConfig,
    entry: UniverseEntry,
    snapshot: dict[str, Any],
) -> PrefilterCandidate | None:
    trade = snapshot.get("latestTrade") if isinstance(snapshot.get("latestTrade"), dict) else {}
    quote = snapshot.get("latestQuote") if isinstance(snapshot.get("latestQuote"), dict) else {}
    minute = snapshot.get("minuteBar") if isinstance(snapshot.get("minuteBar"), dict) else {}
    daily = snapshot.get("dailyBar") if isinstance(snapshot.get("dailyBar"), dict) else {}
    previous = snapshot.get("prevDailyBar") if isinstance(snapshot.get("prevDailyBar"), dict) else {}
    price = _first_number(trade, ["p", "price"]) or _first_number(daily, ["c", "close"])
    ask = _first_number(quote, ["ap", "askPrice"])
    bid = _first_number(quote, ["bp", "bidPrice"])
    if not price and ask and bid:
        price = (ask + bid) / 2
    if not price or price <= 0:
        return None
    previous_close = _first_number(previous, ["c", "close"])
    if not previous_close or previous_close <= 0:
        return None
    daily_volume = _first_number(daily, ["v", "volume"]) or _first_number(minute, ["v", "volume"])
    previous_volume = _first_number(previous, ["v", "volume"])
    change_pct = ((price - previous_close) / previous_close) * 100
    volume_ratio = daily_volume / previous_volume if daily_volume and previous_volume else 1.0
    spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10000) if ask and bid and ask >= bid else 0.0
    as_of = str(trade.get("t") or quote.get("t") or minute.get("t") or "")
    freshness_seconds = _iso_age_seconds(as_of)
    score = _prefilter_score(change_pct, volume_ratio, daily_volume, price, spread_bps)
    return PrefilterCandidate(
        ticker=entry.ticker,
        company_name=entry.name or entry.ticker,
        exchange=entry.exchange,
        latest_price=round(price, 4),
        previous_close=round(previous_close, 4),
        intraday_change_pct=round(change_pct, 2),
        intraday_volume=round(daily_volume or 0.0, 2),
        breakout_volume_ratio=round(volume_ratio, 2),
        spread_bps=round(spread_bps, 2),
        prefilter_score=score,
        source=f"alpaca:{config.alpaca_data_feed}",
        data_as_of=as_of,
        freshness_seconds=round(freshness_seconds, 2),
    )


def _snapshot_from_prefilter(candidate: PrefilterCandidate) -> StockSnapshot:
    volume_z = 0.0
    if candidate.breakout_volume_ratio >= 3:
        volume_z = 3.0
    elif candidate.breakout_volume_ratio >= 2:
        volume_z = 2.5
    elif candidate.breakout_volume_ratio >= 1.5:
        volume_z = 1.8
    surge_score = _surge_score(candidate.intraday_change_pct, candidate.breakout_volume_ratio)
    quality = "realtime-intraday"
    if "delayed" in candidate.source:
        quality = "delayed-intraday"
    elif candidate.freshness_seconds > 900:
        quality = "stale-intraday"
    return StockSnapshot(
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        price=candidate.latest_price,
        breakout_volume_ratio=max(0.0, candidate.breakout_volume_ratio),
        volume_z_score_30d=volume_z,
        source=candidate.source,
        data_as_of=candidate.data_as_of or "intraday",
        data_quality=quality,
        surge_score=surge_score,
        intraday_price=candidate.latest_price,
        intraday_change_pct=candidate.intraday_change_pct,
        intraday_volume=candidate.intraday_volume,
        intraday_source=candidate.source,
        intraday_as_of=candidate.data_as_of,
        intraday_freshness_seconds=candidate.freshness_seconds,
    )


def _prefilter_score(
    change_pct: float,
    volume_ratio: float,
    daily_volume: float,
    price: float,
    spread_bps: float,
) -> int:
    score = 0
    score += min(35, max(0, int(change_pct * 5)))
    score += min(25, max(0, int((volume_ratio - 1) * 16)))
    dollar_volume = max(0.0, daily_volume * price)
    score += min(25, int(math.log10(dollar_volume) * 3) if dollar_volume >= 100_000 else 0)
    score += 10 if 2 <= price <= 250 else 3 if price > 0 else 0
    if spread_bps > 100:
        score -= 15
    elif spread_bps > 50:
        score -= 8
    return max(0, min(100, score))


def _surge_score(change_pct: float, volume_ratio: float) -> int:
    score = min(55, max(0, int(change_pct * 8)))
    score += min(45, max(0, int((volume_ratio - 1) * 22)))
    return max(0, min(100, score))


def _dedupe_entries(entries: list[UniverseEntry]) -> list[UniverseEntry]:
    deduped: dict[str, UniverseEntry] = {}
    for entry in entries:
        if entry.ticker not in deduped:
            deduped[entry.ticker] = entry
    return sorted(deduped.values(), key=lambda item: (item.exchange, item.ticker))


def _prefilter_sort_key(candidate: PrefilterCandidate) -> tuple[int, float, float, str]:
    return (-candidate.prefilter_score, -candidate.intraday_change_pct, -candidate.intraday_volume, candidate.ticker)


def _alpaca_configured(config: AppConfig) -> bool:
    return bool(config.external_api_enabled and config.alpaca_api_key and config.alpaca_api_secret)


def _alpaca_headers(config: AppConfig) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": config.alpaca_api_key,
        "APCA-API-SECRET-KEY": config.alpaca_api_secret,
        "User-Agent": "vcb-alt-stock-screener/0.1",
        "Accept": "application/json,text/plain,*/*",
    }


def _alpaca_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")[:240]
    except Exception:
        body = ""
    if exc.code in {401, 403}:
        return f"Alpaca rejected the market-universe request with HTTP {exc.code}. Check API key, secret, and data feed."
    if exc.code == 429:
        return "Alpaca rate limit reached during market-universe scan."
    return f"Alpaca market-universe request failed with HTTP {exc.code}. {body}".strip()


def _probe_alpaca_endpoint(config: AppConfig, url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_alpaca_headers(config))
    try:
        with urllib.request.urlopen(request, timeout=config.market_data_timeout_seconds) as response:
            return {
                "ok": 200 <= int(response.status) < 300,
                "status_code": int(response.status),
                "message": "accepted",
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status_code": exc.code,
            "message": _alpaca_probe_error_label(exc.code),
            "request_id": _response_header(exc, "x-request-id"),
        }
    except urllib.error.URLError as exc:
        return {"ok": False, "status_code": None, "message": f"network_error:{type(exc.reason).__name__}"}
    except TimeoutError:
        return {"ok": False, "status_code": None, "message": "timeout"}


def _alpaca_probe_error_label(status_code: int) -> str:
    if status_code == 400:
        return "invalid_request"
    if status_code == 401:
        return "invalid_or_mismatched_credentials"
    if status_code == 403:
        return "forbidden_or_feed_not_allowed"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "provider_server_error"
    return "provider_rejected_request"


def _response_header(exc: urllib.error.HTTPError, name: str) -> str:
    try:
        return str(exc.headers.get(name) or exc.headers.get(name.upper()) or "")
    except Exception:
        return ""


def _alpaca_diagnostic_classification(trading: dict[str, Any], market_data: dict[str, Any]) -> str:
    if any(item.get("ok") for item in trading.values()) and market_data.get("ok"):
        return "ready"
    trading_codes = {int(item["status_code"]) for item in trading.values() if item.get("status_code")}
    market_code = int(market_data["status_code"]) if market_data.get("status_code") else None
    if 401 in trading_codes or market_code == 401:
        return "key_context_mismatch_or_invalid"
    if market_code == 403:
        return "feed_forbidden"
    if 429 in trading_codes or market_code == 429:
        return "rate_limited"
    if not any(item.get("ok") for item in trading.values()):
        return "trading_context_not_accepted"
    return "market_data_not_accepted"


def _alpaca_diagnostic_next_actions(classification: str, feed: str) -> list[str]:
    if classification == "ready":
        return ["Run /api/user/scan and verify prefilter.source starts with alpaca."]
    if classification == "key_context_mismatch_or_invalid":
        return [
            "Regenerate the Alpaca Key ID and Secret Key as one matching pair.",
            "Confirm the pair belongs to the intended Paper or Live account, then update both Vercel Production variables.",
            "Redeploy after changing Vercel environment variables.",
        ]
    if classification == "feed_forbidden":
        return [
            f"The configured feed '{feed}' is not allowed for this Alpaca account.",
            "Use VCB_ALT_ALPACA_DATA_FEED=iex unless the account has SIP access.",
            "Redeploy after changing Vercel environment variables.",
        ]
    if classification == "rate_limited":
        return ["Wait for the Alpaca rate-limit window to reset, then rerun diagnostics before scanning."]
    if classification == "trading_context_not_accepted":
        return ["Check whether the credentials are Paper or Live keys and whether the trading account is active."]
    return ["Check Alpaca provider status and rerun diagnostics; keep production scan fail-closed until ready=true."]


def _read_fresh_cache(path: Path, ttl_seconds: float) -> str | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl_seconds:
        return None
    return path.read_text(encoding="utf-8")


def _market_scan_report_cache_path(
    config: AppConfig,
    universe_limit: int | None,
    prefilter_limit: int | None,
    max_positions: int,
) -> Path:
    raw_key = json.dumps(
        {
            "provider": config.market_universe_provider,
            "max_symbols": universe_limit or config.market_universe_max_symbols,
            "prefilter": prefilter_limit or config.market_prefilter_limit,
            "positions": max_positions,
            "feed": config.alpaca_data_feed,
            "research": config.research_data_provider,
            "live_required": config.market_scan_requires_live_data,
            "scan_version": "market-v1",
        },
        sort_keys=True,
    )
    key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return config.data_dir / "market_universe" / "scan_reports" / UNIVERSE_CACHE_VERSION / f"{key}.json"


def _write_market_scan_report_cache(path: Path, result: MarketScanResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_api_dict(), ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _market_scan_result_from_json(raw: str) -> MarketScanResult:
    data = json.loads(raw)
    evaluations = [EvaluationResult(**item) for item in data.get("items", [])]
    selected = [EvaluationResult(**item) for item in data.get("selection", {}).get("selected", [])]
    selection_data = data.get("selection", {})
    selection = PortfolioSelection(
        selected=selected,
        rejected=list(selection_data.get("rejected", [])),
        max_positions=int(selection_data.get("max_positions", 3)),
        max_total_size_pct=float(selection_data.get("max_total_size_pct", 75.0)),
        total_size_pct=float(selection_data.get("total_size_pct", 0.0)),
        data_provider=str(selection_data.get("data_provider", "cached")),
    )
    return MarketScanResult(
        evaluations=evaluations,
        failures=list(data.get("failures", [])),
        selection=selection,
        elapsed_ms=int(data.get("elapsed_ms", 0)),
        universe=dict(data.get("universe", {})),
        prefilter=dict(data.get("prefilter", {})),
    )


def _first_number(container: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = container.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _iso_age_seconds(value: str) -> float:
    if not value:
        return 0.0
    try:
        from datetime import datetime, timezone

        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        return 0.0

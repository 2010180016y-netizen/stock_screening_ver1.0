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
from .providers import apply_research_enrichment, get_snapshot
from .sample_data import SAMPLE_TICKERS
from .scoring import evaluate_snapshot
from .validation import validate_ticker

ALPACA_TRADING_BASE_URLS = ("https://paper-api.alpaca.markets", "https://api.alpaca.markets")
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"
UNIVERSE_CACHE_VERSION = "v1"


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
            cached_result.prefilter["cache"] = "hit"
            return cached_result
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            cache_path.unlink(missing_ok=True)

    start = time.perf_counter()
    limit = min(universe_limit or config.market_universe_max_symbols, config.market_universe_max_symbols)
    entries, universe_meta = load_market_universe(config, limit=limit)
    candidates, prefilter_meta = prefilter_market_candidates(config, entries, limit=prefilter_limit)
    failures: list[dict[str, Any]] = []

    if candidates:
        evaluations = _evaluate_prefiltered_candidates(config, candidates, failures)
    else:
        if config.market_scan_requires_live_data:
            raise ValidationError(
                "Market-universe scan requires live Alpaca snapshots, but no live candidates were available."
            )
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
    result.prefilter["cache"] = "miss"
    _write_market_scan_report_cache(cache_path, result)
    return result


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
            with urllib.request.urlopen(request, timeout=config.market_data_timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {401, 403}:
                raise ValidationError(_alpaca_error_message(exc)) from exc
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            continue
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
        try:
            with urllib.request.urlopen(request, timeout=config.market_data_timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ValidationError(_alpaca_error_message(exc)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValidationError(f"Alpaca snapshot request failed: {exc}") from exc
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(body, encoding="utf-8")
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

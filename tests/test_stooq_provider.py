from __future__ import annotations

import tempfile
import unittest
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import vcb_alt.providers as providers
from vcb_alt.config import AppConfig
from vcb_alt.providers import MarketBar, build_snapshot_from_bars, get_price_history, get_snapshot, get_ticker_profile
from vcb_alt.scoring import evaluate_snapshot


def make_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="stooq",
        external_api_enabled=True,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
    )


def make_yahoo_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="yahoo",
        external_api_enabled=True,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
    )


def make_finnhub_yahoo_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="yahoo",
        external_api_enabled=True,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
        research_data_provider="finnhub",
        finnhub_api_key="test-token",
    )


def make_full_data_yahoo_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="yahoo",
        external_api_enabled=True,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
        intraday_data_provider="alpaca",
        alpaca_api_key="test-key",
        alpaca_api_secret="test-secret",
        research_data_provider="finnhub",
        finnhub_api_key="test-token",
        sec_company_facts_enabled=True,
    )


def make_trending_bars(count: int = 260) -> list[MarketBar]:
    start = date.today() - timedelta(days=count)
    bars: list[MarketBar] = []
    for index in range(count):
        close = 50.0 + index * 0.4
        volume = 1_000_000.0
        if index == count - 1:
            volume = 2_400_000.0
        bars.append(
            MarketBar(
                date=start + timedelta(days=index),
                open=close - 0.2,
                high=close + 0.6,
                low=close - 0.8,
                close=close,
                volume=volume,
            )
        )
    return bars


class StooqProviderTests(unittest.TestCase):
    def test_build_snapshot_from_bars_computes_trend_and_surge_metrics(self) -> None:
        snapshot = build_snapshot_from_bars("AAPL", make_trending_bars(), make_trending_bars(), source="stooq")
        self.assertEqual(snapshot.ticker, "AAPL")
        self.assertEqual(snapshot.source, "stooq")
        self.assertTrue(snapshot.above_200dma)
        self.assertGreaterEqual(snapshot.trend_template_score, 80)
        self.assertGreaterEqual(snapshot.surge_score, 40)
        self.assertGreater(snapshot.breakout_volume_ratio, 2.0)
        self.assertGreater(snapshot.return_12w_pct, 0)

        result = evaluate_snapshot(snapshot)
        self.assertEqual(result.primary_archetype, "G_TECHNICAL_MOMENTUM")
        self.assertFalse(result.can_enter)
        self.assertEqual(result.data_coverage_label, "price-volume-only")
        self.assertIn("blocked until enrichment data is present", " ".join(result.rationale))

    def test_stooq_provider_reads_fresh_cache_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "data" / "market_cache" / "stooq" / "v1"
            cache_dir.mkdir(parents=True)
            rows = ["Date,Open,High,Low,Close,Volume"]
            for bar in make_trending_bars():
                rows.append(f"{bar.date.isoformat()},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}")
            (cache_dir / "aapl.csv").write_text("\n".join(rows), encoding="utf-8")

            snapshot = get_snapshot(make_config(root), "AAPL")

            self.assertEqual(snapshot.ticker, "AAPL")
            self.assertEqual(snapshot.source, "stooq")
            self.assertGreaterEqual(snapshot.trend_template_score, 80)

    def test_yahoo_provider_reads_fresh_cache_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "data" / "market_cache" / "yahoo" / "v1"
            cache_dir.mkdir(parents=True)
            bars = make_trending_bars()
            payload = yahoo_payload("AAPL", "Apple Inc.", bars)
            (cache_dir / "aapl.json").write_text(json.dumps(payload), encoding="utf-8")
            (cache_dir / "spy.json").write_text(json.dumps(yahoo_payload("SPY", "SPDR S&P 500 ETF", bars)), encoding="utf-8")

            snapshot = get_snapshot(make_yahoo_config(root), "AAPL")

            self.assertEqual(snapshot.ticker, "AAPL")
            self.assertEqual(snapshot.company_name, "Apple Inc.")
            self.assertEqual(snapshot.source, "yahoo")
            self.assertGreaterEqual(snapshot.trend_template_score, 80)

    def test_yahoo_process_cache_refreshes_when_ttl_bucket_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "data" / "market_cache" / "yahoo" / "v1"
            cache_dir.mkdir(parents=True)
            providers._load_yahoo_bars_cached.cache_clear()
            original_bucket = providers._ttl_bucket
            buckets = iter([1, 1, 2])
            bars = make_trending_bars()
            cache_path = cache_dir / "aapl.json"
            cache_path.write_text(json.dumps(yahoo_payload("AAPL", "Apple v1", bars)), encoding="utf-8")

            try:
                providers._ttl_bucket = lambda _cache_ttl_hours: next(buckets)  # type: ignore[assignment]
                first_bars, first_name = providers._load_yahoo_bars(str(root / "data"), "AAPL", 1.0, 12.0)
                cache_path.write_text(json.dumps(yahoo_payload("AAPL", "Apple v2", bars)), encoding="utf-8")
                second_bars, second_name = providers._load_yahoo_bars(str(root / "data"), "AAPL", 1.0, 12.0)
                third_bars, third_name = providers._load_yahoo_bars(str(root / "data"), "AAPL", 1.0, 12.0)
            finally:
                providers._ttl_bucket = original_bucket  # type: ignore[assignment]
                providers._load_yahoo_bars_cached.cache_clear()

            self.assertEqual(first_name, "Apple v1")
            self.assertEqual(second_name, "Apple v1")
            self.assertEqual(third_name, "Apple v2")
            self.assertEqual(len(first_bars), len(second_bars))
            self.assertEqual(len(second_bars), len(third_bars))

    def test_yahoo_provider_applies_manual_enrichment_for_entry_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            cache_dir = data_dir / "market_cache" / "yahoo" / "v1"
            cache_dir.mkdir(parents=True)
            bars = make_trending_bars()
            (cache_dir / "pltr.json").write_text(
                json.dumps(yahoo_payload("PLTR", "Palantir Technologies Inc.", bars)),
                encoding="utf-8",
            )
            (cache_dir / "spy.json").write_text(
                json.dumps(yahoo_payload("SPY", "SPDR S&P 500 ETF", bars)),
                encoding="utf-8",
            )
            (data_dir / "enrichment.csv").write_text(
                "ticker,revenue_surprise_pct,revenue_acceleration_pp,insider_buy_count_90d,"
                "forward_guidance_raised,news_catalyst_30d,float_shares_m,eps_revision_pct,"
                "enrichment_source,enrichment_as_of\n"
                "PLTR,30,8,2,true,true,2200,24,operator-research,2026-05-20\n",
                encoding="utf-8",
            )

            snapshot = get_snapshot(make_yahoo_config(root), "PLTR")
            result = evaluate_snapshot(snapshot)

            self.assertEqual(snapshot.source, "yahoo+operator-research")
            self.assertEqual(snapshot.enrichment_source, "operator-research")
            self.assertGreaterEqual(result.data_coverage_score, 80)
            self.assertTrue(result.can_enter)

    def test_yahoo_provider_applies_finnhub_research_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            market_cache = data_dir / "market_cache" / "yahoo" / "v1"
            research_cache = data_dir / "research_cache" / "finnhub" / "v1"
            market_cache.mkdir(parents=True)
            research_cache.mkdir(parents=True)
            bars = make_trending_bars()
            (market_cache / "pltr.json").write_text(
                json.dumps(yahoo_payload("PLTR", "Palantir Technologies Inc.", bars)),
                encoding="utf-8",
            )
            (market_cache / "spy.json").write_text(
                json.dumps(yahoo_payload("SPY", "SPDR S&P 500 ETF", bars)),
                encoding="utf-8",
            )
            write_finnhub_cache(research_cache, "pltr")

            snapshot = get_snapshot(make_finnhub_yahoo_config(root), "PLTR")
            result = evaluate_snapshot(snapshot)

            self.assertEqual(snapshot.source, "yahoo+finnhub")
            self.assertEqual(snapshot.enrichment_source, "finnhub")
            self.assertGreater(snapshot.short_interest_pct, 0)
            self.assertGreater(snapshot.call_open_interest, 0)
            self.assertTrue(snapshot.news_catalyst_30d)
            self.assertGreaterEqual(result.data_coverage_score, 80)
            self.assertTrue(result.can_enter)

    def test_full_data_layers_apply_from_local_caches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            market_cache = data_dir / "market_cache" / "yahoo" / "v1"
            research_cache = data_dir / "research_cache" / "finnhub" / "v1"
            intraday_cache = data_dir / "intraday_cache" / "alpaca" / "v1"
            sec_cache = data_dir / "research_cache" / "sec" / "v1"
            market_cache.mkdir(parents=True)
            research_cache.mkdir(parents=True)
            intraday_cache.mkdir(parents=True)
            (sec_cache / "submissions").mkdir(parents=True)
            bars = make_trending_bars()
            (market_cache / "pltr.json").write_text(
                json.dumps(yahoo_payload("PLTR", "Palantir Technologies Inc.", bars)),
                encoding="utf-8",
            )
            (market_cache / "spy.json").write_text(
                json.dumps(yahoo_payload("SPY", "SPDR S&P 500 ETF", bars)),
                encoding="utf-8",
            )
            write_finnhub_cache(research_cache, "pltr")
            write_alpaca_cache(intraday_cache, "pltr")
            write_sec_cache(sec_cache, "0001321655")

            snapshot = get_snapshot(make_full_data_yahoo_config(root), "PLTR")
            result = evaluate_snapshot(snapshot)

            self.assertEqual(snapshot.intraday_source, "alpaca")
            self.assertEqual(snapshot.intraday_price, 123.45)
            self.assertGreater(snapshot.analyst_buy_count, 0)
            self.assertTrue(snapshot.filing_catalyst_30d)
            self.assertEqual(snapshot.latest_filing_type, "8-K")
            self.assertGreaterEqual(result.data_coverage_score, 80)

    def test_sample_history_and_profile_are_available_for_detail_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                database_url="sqlite:///./data/test.db",
                log_level="INFO",
                timezone="Asia/Seoul",
                data_provider="sample",
                external_api_enabled=False,
                root_dir=root,
                data_dir=root / "data",
                log_dir=root / "logs",
            )
            history = get_price_history(config, "PLTR", years=5)
            snapshot = get_snapshot(config, "PLTR")
            profile = get_ticker_profile(config, "PLTR", snapshot=snapshot)
            self.assertEqual(history["range"], "5y")
            self.assertFalse(history["is_realtime"])
            self.assertGreaterEqual(len(history["points"]), 1000)
            self.assertEqual(profile["sector"], "Technology")
            self.assertIn("Software", profile["industry"])


def yahoo_payload(symbol: str, long_name: str, bars: list[MarketBar]) -> dict[str, object]:
    timestamps = [
        int(datetime.combine(bar.date, time(16, 0), timezone.utc).timestamp())
        for bar in bars
    ]
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": symbol, "longName": long_name},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [bar.open for bar in bars],
                                "high": [bar.high for bar in bars],
                                "low": [bar.low for bar in bars],
                                "close": [bar.close for bar in bars],
                                "volume": [bar.volume for bar in bars],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def write_finnhub_cache(cache_dir: Path, ticker: str) -> None:
    payloads = {
        "metric": {
            "metric": {
                "marketCapitalization": 285000,
                "floatShares": 2200,
                "revenueGrowthQuarterlyYoy": 8,
                "epsGrowthQuarterlyYoy": 24,
            }
        },
        "earnings": [{"actual": 0.08, "estimate": 0.06, "surprisePercent": 33.3}],
        "news": [
            {
                "headline": "Palantir wins AI infrastructure contract and raises guidance",
                "summary": "Data center AI infrastructure demand supports the quarter.",
            }
        ],
        "insider": {"data": [{"transactionCode": "P", "share": 1000}, {"transactionCode": "P", "share": 500}]},
        "short_interest": {"data": [{"shortPercent": 6.5, "daysToCover": 2.4}]},
        "option_chain": {
            "data": [
                {
                    "options": {
                        "CALL": [{"openInterest": 1200}, {"openInterest": 800}],
                        "PUT": [{"openInterest": 600}],
                    }
                }
            ]
        },
        "recommendation": [{"strongBuy": 8, "buy": 12, "hold": 6, "sell": 1, "strongSell": 0}],
    }
    for name, payload in payloads.items():
        (cache_dir / f"{ticker}_{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def write_alpaca_cache(cache_dir: Path, ticker: str) -> None:
    payload = {
        "snapshots": {
            ticker.upper(): {
                "latestTrade": {"p": 123.45, "t": "2026-05-20T15:59:00Z"},
                "latestQuote": {"ap": 123.5, "bp": 123.4, "t": "2026-05-20T15:59:00Z"},
                "minuteBar": {"c": 123.45, "v": 500000, "t": "2026-05-20T15:59:00Z"},
                "dailyBar": {"c": 123.45, "v": 12000000},
                "prevDailyBar": {"c": 120.0},
            }
        }
    }
    (cache_dir / f"{ticker}_snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def write_sec_cache(cache_dir: Path, cik: str) -> None:
    (cache_dir / "company_tickers.json").write_text(
        json.dumps({"0": {"cik_str": int(cik), "ticker": "PLTR", "title": "Palantir Technologies Inc."}}),
        encoding="utf-8",
    )
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q"],
                "filingDate": [date.today().isoformat(), "2026-04-30"],
                "accessionNumber": ["0001321655-26-000001", "0001321655-26-000002"],
                "primaryDocument": ["pltr-20260520.htm", "pltr-20260430.htm"],
            }
        }
    }
    (cache_dir / "submissions" / f"{cik}.json").write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

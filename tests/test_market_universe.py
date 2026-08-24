from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from vcb_alt.config import AppConfig
from vcb_alt.errors import NotFoundError, ValidationError
from vcb_alt import market_universe, providers
from vcb_alt.market_universe import (
    UNIVERSE_CACHE_VERSION,
    UniverseEntry,
    _market_scan_report_cache_path,
    _resolve_prefilter_provider,
    diagnose_alpaca_credentials,
    prefilter_market_candidates,
    scan_market_universe,
)


def make_config(root: Path, **overrides: object) -> AppConfig:
    values = {
        "database_url": "sqlite:///./data/test.db",
        "log_level": "INFO",
        "timezone": "Asia/Seoul",
        "data_provider": "sample",
        "external_api_enabled": False,
        "root_dir": root,
        "data_dir": root / "data",
        "log_dir": root / "logs",
        "scan_mode": "market_universe",
    }
    values.update(overrides)
    return AppConfig(**values)


class MarketUniverseTests(unittest.TestCase):
    def test_market_scan_falls_back_to_sample_with_clear_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            report = scan_market_universe(config, prefilter_limit=3)

            data = report.to_api_dict()
            self.assertEqual(data["scan_mode"], "market_universe")
            self.assertEqual(data["universe"]["source"], "sample")
            self.assertEqual(data["prefilter"]["fallback"], "sample_universe")
            self.assertGreaterEqual(data["count"], 3)
            self.assertIn("selection", data)

    def test_live_data_required_blocks_sample_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp), market_scan_requires_live_data=True)

            with self.assertRaises(ValidationError) as raised:
                scan_market_universe(config, prefilter_limit=3)

            message = str(raised.exception)
            self.assertIn("Fail-closed", message)
            self.assertIn("Sample/demo fallback is disabled", message)

    def test_live_data_required_ignores_stale_sample_scan_report_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_config = make_config(root)
            sample_report = scan_market_universe(local_config, prefilter_limit=3)
            live_config = make_config(root, market_scan_requires_live_data=True)
            live_cache = _market_scan_report_cache_path(live_config, None, 3, 3)
            live_cache.parent.mkdir(parents=True, exist_ok=True)
            live_cache.write_text(json.dumps(sample_report.to_api_dict()), encoding="utf-8")

            with self.assertRaises(ValidationError):
                scan_market_universe(live_config, prefilter_limit=3)

            self.assertFalse(live_cache.exists())

    def test_market_scan_uses_cached_alpaca_snapshots_before_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "universe.csv").write_text(
                "ticker,name,exchange,tradable\n"
                "PLTR,Palantir Technologies Inc.,NASDAQ,true\n"
                "VST,Vistra Corp.,NYSE,true\n",
                encoding="utf-8",
            )
            (data_dir / "enrichment.csv").write_text(
                "ticker,revenue_surprise_pct,revenue_acceleration_pp,"
                "data_center_narrative,eps_revision_pct,news_catalyst_30d,float_shares_m,"
                "short_interest_pct,call_oi_change_pct,enrichment_source,enrichment_as_of\n"
                "PLTR,30,8,false,25,true,2200,6,25,operator-research,2026-05-26\n"
                "VST,15,4,true,30,true,480,4,10,operator-research,2026-05-26\n",
                encoding="utf-8",
            )
            symbols = "PLTR,VST"
            key = hashlib.sha256((symbols + ":iex").encode("utf-8")).hexdigest()[:24]
            cache_dir = data_dir / "market_universe" / "alpaca" / UNIVERSE_CACHE_VERSION / "snapshots"
            cache_dir.mkdir(parents=True)
            (cache_dir / f"{key}.json").write_text(json.dumps(alpaca_snapshot_payload()), encoding="utf-8")

            config = make_config(
                root,
                external_api_enabled=True,
                alpaca_api_key="key",
                alpaca_api_secret="secret",
                market_universe_provider="csv",
                market_prefilter_limit=2,
                market_scan_requires_live_data=True,
            )
            report = scan_market_universe(config)
            data = report.to_api_dict()

            self.assertEqual(data["universe"]["source"], "csv")
            self.assertEqual(data["prefilter"]["source"], "alpaca:iex")
            self.assertEqual(data["count"], 2)
            self.assertTrue(all(item["source"].startswith("alpaca:iex") for item in data["items"]))
            self.assertTrue(any(item["can_enter"] for item in data["items"]))

    def test_alpaca_diagnostics_classifies_invalid_credentials_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(
                Path(tmp),
                external_api_enabled=True,
                alpaca_api_key="alpaca-key-id",
                alpaca_api_secret="alpaca-secret-value",
            )
            error = urllib.error.HTTPError(
                url="https://data.alpaca.markets/v2/stocks/snapshots",
                code=401,
                msg="Unauthorized",
                hdrs={"x-request-id": "req-test"},
                fp=None,
            )
            with patch("vcb_alt.market_universe.urllib.request.urlopen", side_effect=error):
                result = diagnose_alpaca_credentials(config)

            rendered = json.dumps(result)
            self.assertFalse(result["ready"])
            self.assertEqual(result["classification"], "key_context_mismatch_or_invalid")
            self.assertEqual(result["trading"]["paper"]["status_code"], 401)
            self.assertEqual(result["market_data"]["snapshot"]["status_code"], 401)
            self.assertNotIn("alpaca-key-id", rendered)
            self.assertNotIn("alpaca-secret-value", rendered)

    def test_alpaca_diagnostics_reports_ready_when_trading_and_data_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(
                Path(tmp),
                external_api_enabled=True,
                alpaca_api_key="key",
                alpaca_api_secret="secret",
            )
            with patch("vcb_alt.market_universe.urllib.request.urlopen", return_value=_FakeAlpacaResponse()):
                result = diagnose_alpaca_credentials(config, symbol="msft")

            self.assertTrue(result["ready"])
            self.assertEqual(result["classification"], "ready")
            self.assertEqual(result["market_data"]["test_symbol"], "MSFT")


def alpaca_snapshot_payload() -> dict[str, object]:
    return {
        "snapshots": {
            "PLTR": {
                "latestTrade": {"p": 130.0, "t": "2026-05-26T15:59:00Z"},
                "latestQuote": {"ap": 130.1, "bp": 129.9, "t": "2026-05-26T15:59:00Z"},
                "minuteBar": {"c": 130.0, "v": 250000, "t": "2026-05-26T15:59:00Z"},
                "dailyBar": {"c": 130.0, "v": 14000000},
                "prevDailyBar": {"c": 120.0, "v": 7000000},
            },
            "VST": {
                "latestTrade": {"p": 160.0, "t": "2026-05-26T15:59:00Z"},
                "latestQuote": {"ap": 160.2, "bp": 159.8, "t": "2026-05-26T15:59:00Z"},
                "minuteBar": {"c": 160.0, "v": 200000, "t": "2026-05-26T15:59:00Z"},
                "dailyBar": {"c": 160.0, "v": 9000000},
                "prevDailyBar": {"c": 150.0, "v": 5000000},
            },
        }
    }


class _FakeAlpacaResponse:
    status = 200

    def __enter__(self) -> "_FakeAlpacaResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


if __name__ == "__main__":
    unittest.main()


def _prefilter_config(root: Path, **overrides: object) -> AppConfig:
    base = {
        "database_url": "sqlite:///./data/test.db",
        "log_level": "INFO",
        "timezone": "Asia/Seoul",
        "data_provider": "sample",
        "external_api_enabled": False,
        "root_dir": root,
        "data_dir": root / "data",
        "log_dir": root / "logs",
    }
    base.update(overrides)
    return AppConfig(**base)  # type: ignore[arg-type]


def _fake_history(_config: object, ticker: str, years: int = 1) -> dict[str, object]:
    table = {
        "AAPL": (100.0, 101.0, 1_000_000.0, 1_100_000.0),
        "NVDA": (100.0, 112.0, 1_000_000.0, 4_000_000.0),
        "KO": (100.0, 99.5, 1_000_000.0, 900_000.0),
    }
    previous_close, close, previous_volume, volume = table[ticker]
    return {
        "ticker": ticker,
        "source": "yahoo",
        "points": [
            {"date": "2026-08-21", "close": previous_close, "volume": previous_volume},
            {"date": "2026-08-22", "close": close, "volume": volume},
        ],
    }


class PrefilterProviderTests(unittest.TestCase):
    """The prefilter used to be Alpaca-only, which made it the single point of failure.

    With no prefilter the scan returns nothing no matter how healthy the other
    providers are, which is exactly what a bad Alpaca credential produced.
    """

    def test_provider_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_resolve_prefilter_provider(_prefilter_config(root)), "none")
            self.assertEqual(
                _resolve_prefilter_provider(
                    _prefilter_config(root, data_provider="yahoo", external_api_enabled=True)
                ),
                "yahoo",
            )
            self.assertEqual(
                _resolve_prefilter_provider(
                    _prefilter_config(
                        root, external_api_enabled=True, alpaca_api_key="k", alpaca_api_secret="s"
                    )
                ),
                "alpaca",
            )
            # An explicit choice always wins over the automatic one.
            self.assertEqual(
                _resolve_prefilter_provider(
                    _prefilter_config(
                        root,
                        market_prefilter_provider="none",
                        external_api_enabled=True,
                        alpaca_api_key="k",
                        alpaca_api_secret="s",
                    )
                ),
                "none",
            )

    def test_yahoo_prefilter_ranks_candidates_without_any_credential(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(Path(tmp), data_provider="yahoo", external_api_enabled=True)
            entries = [
                UniverseEntry(ticker=ticker, name=ticker, exchange="NASDAQ", source="csv")
                for ticker in ("AAPL", "NVDA", "KO")
            ]
            with patch.object(market_universe, "get_price_history", side_effect=_fake_history):
                candidates, meta = prefilter_market_candidates(config, entries, limit=2)

            self.assertEqual(meta["source"], "yahoo:eod")
            self.assertEqual([item.ticker for item in candidates], ["NVDA", "AAPL"])
            self.assertEqual(candidates[0].intraday_change_pct, 12.0)
            self.assertEqual(candidates[0].breakout_volume_ratio, 4.0)
            # No bid/ask exists in daily bars, and the label must say end-of-day.
            self.assertEqual(candidates[0].spread_bps, 0.0)
            self.assertIn("end-of-day", meta["warnings"][0].lower())
            # The scoring pipeline must accept what this path produces.
            with patch.object(market_universe, "get_snapshot") as snapshot:
                market_universe._snapshot_for_candidate(config, candidates[0])
            snapshot.assert_called_once_with(config, "NVDA")

    def test_yahoo_prefilter_caps_the_number_of_symbols_it_fetches(self) -> None:
        """One request per symbol, so an unbounded universe would be a request storm."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(
                Path(tmp),
                data_provider="yahoo",
                external_api_enabled=True,
                yahoo_prefilter_max_symbols=2,
            )
            entries = [
                UniverseEntry(ticker=ticker, name=ticker, exchange="NASDAQ", source="csv")
                for ticker in ("AAPL", "NVDA", "KO")
            ]
            with patch.object(market_universe, "get_price_history", side_effect=_fake_history) as fetch:
                _, meta = prefilter_market_candidates(config, entries)

            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(meta["scanned_symbols"], 2)
            self.assertTrue(any("first 2 of 3" in warning for warning in meta["warnings"]))

    def test_no_provider_explains_both_ways_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(Path(tmp))
            entries = [UniverseEntry(ticker="AAPL", name="Apple", exchange="NASDAQ", source="csv")]
            candidates, meta = prefilter_market_candidates(config, entries)
            self.assertEqual(candidates, [])
            self.assertEqual(meta["source"], "unavailable")
            self.assertIn("Alpaca", meta["warnings"][0])
            self.assertIn("VCB_ALT_MARKET_PREFILTER_PROVIDER=yahoo", meta["warnings"][0])


class PrefilterSnapshotTests(unittest.TestCase):
    def test_end_of_day_candidates_use_the_provider_snapshot_path(self) -> None:
        """A hand-built snapshot loses the trend score and is labelled stale intraday.

        That scored the momentum archetype at zero, so no end-of-day candidate could ever
        be selected however strong its move was.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(Path(tmp), data_provider="yahoo", external_api_enabled=True)
            eod = market_universe.PrefilterCandidate(
                ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", latest_price=112.0,
                previous_close=100.0, intraday_change_pct=12.0, intraday_volume=4_000_000.0,
                breakout_volume_ratio=4.0, spread_bps=0.0, prefilter_score=95,
                source="yahoo:eod", data_as_of="2026-08-22", freshness_seconds=86400.0,
            )
            with patch.object(market_universe, "get_snapshot") as snapshot:
                market_universe._snapshot_for_candidate(config, eod)
            snapshot.assert_called_once_with(config, "NVDA")

    def test_intraday_candidates_still_convert_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(Path(tmp))
            intraday = market_universe.PrefilterCandidate(
                ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", latest_price=112.0,
                previous_close=100.0, intraday_change_pct=12.0, intraday_volume=4_000_000.0,
                breakout_volume_ratio=4.0, spread_bps=2.0, prefilter_score=95,
                source="alpaca:iex", data_as_of="2026-08-22T13:00:00Z", freshness_seconds=30.0,
            )
            with patch.object(market_universe, "get_snapshot") as snapshot:
                built = market_universe._snapshot_for_candidate(config, intraday)
            snapshot.assert_not_called()
            self.assertEqual(built.source, "alpaca:iex")

    def test_prefilter_stops_at_the_time_budget(self) -> None:
        """One request per symbol overruns any serverless execution limit unbounded."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(
                Path(tmp),
                data_provider="yahoo",
                external_api_enabled=True,
                prefilter_time_budget_seconds=0.05,
            )
            entries = [
                UniverseEntry(ticker=ticker, name=ticker, exchange="NASDAQ", source="csv")
                for ticker in ("AAPL", "NVDA", "KO")
            ]

            def slow_history(_config: object, ticker: str, years: int = 1) -> dict[str, object]:
                time.sleep(0.04)
                return _fake_history(_config, ticker, years)

            with patch.object(market_universe, "get_price_history", side_effect=slow_history):
                _, meta = prefilter_market_candidates(config, entries)

            self.assertTrue(meta["time_budget_exhausted"])
            self.assertLess(meta["scanned_symbols"], len(entries))
            self.assertEqual(meta["skipped_symbols"], len(entries) - meta["scanned_symbols"])
            self.assertTrue(any("time budget" in warning for warning in meta["warnings"]))


class OperatorCsvPathTests(unittest.TestCase):
    """These files used to resolve only under root_dir, so setting DATA_DIR and putting
    them there produced a silent fallback: no universe, and enrichment that never applied.
    """

    def test_operator_csvs_resolve_from_the_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "elsewhere"
            data_dir.mkdir()
            config = _prefilter_config(root, data_dir=data_dir)
            for name in ("universe.csv", "enrichment.csv", "snapshots.csv"):
                (data_dir / name).write_text("ticker" + chr(10), encoding="utf-8")

            self.assertEqual(market_universe.market_universe_path(config), data_dir / "universe.csv")
            self.assertEqual(providers.enrichment_snapshot_path(config), data_dir / "enrichment.csv")
            self.assertEqual(providers.manual_snapshot_path(config), data_dir / "snapshots.csv")

    def test_legacy_root_location_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "data"
            legacy.mkdir()
            (legacy / "universe.csv").write_text("ticker" + chr(10), encoding="utf-8")
            config = _prefilter_config(root, data_dir=root / "not-here")
            self.assertEqual(market_universe.market_universe_path(config), legacy / "universe.csv")


class WatchlistUniverseTests(unittest.TestCase):
    """Adding a ticker in the sidebar used to change nothing about the scan."""

    def _config(self, root: Path, **overrides: object) -> AppConfig:
        return _prefilter_config(root, scan_mode="market_universe", **overrides)

    def test_watchlist_becomes_the_universe(self) -> None:
        from vcb_alt.db import add_watchlist, connect, init_db

        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                add_watchlist(conn, ["AAPL", "MSFT"])
                entries, meta = market_universe.load_market_universe(config, conn=conn)

            self.assertEqual(meta["source"], "watchlist")
            self.assertEqual(sorted(entry.ticker for entry in entries), ["AAPL", "MSFT"])

    def test_sample_fallback_only_when_nothing_else_exists(self) -> None:
        from vcb_alt.db import connect, init_db

        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                _, meta = market_universe.load_market_universe(config, conn=conn)
            self.assertEqual(meta["source"], "sample")

    def test_without_a_connection_behaviour_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(Path(tmp))
            _, meta = market_universe.load_market_universe(config)
            self.assertEqual(meta["source"], "sample")


class CachedSelectionTests(unittest.TestCase):
    def test_rebuilding_a_selection_without_a_scan_says_so(self) -> None:
        """Rebuild used to repeat the whole provider-heavy sweep instead of reusing it."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _prefilter_config(Path(tmp), scan_mode="market_universe")
            with self.assertRaises(NotFoundError) as caught:
                market_universe.scan_market_universe(config, cached_only=True)
            self.assertIn("Run a market scan first", str(caught.exception))

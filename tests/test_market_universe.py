from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from vcb_alt.config import AppConfig
from vcb_alt.market_universe import scan_market_universe


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
            cache_dir = data_dir / "market_universe" / "alpaca" / "v1" / "snapshots"
            cache_dir.mkdir(parents=True)
            (cache_dir / f"{key}.json").write_text(json.dumps(alpaca_snapshot_payload()), encoding="utf-8")

            config = make_config(
                root,
                external_api_enabled=True,
                alpaca_api_key="key",
                alpaca_api_secret="secret",
                market_universe_provider="csv",
                market_prefilter_limit=2,
            )
            report = scan_market_universe(config)
            data = report.to_api_dict()

            self.assertEqual(data["universe"]["source"], "csv")
            self.assertEqual(data["prefilter"]["source"], "alpaca:iex")
            self.assertEqual(data["count"], 2)
            self.assertTrue(all(item["source"].startswith("alpaca:iex") for item in data["items"]))
            self.assertTrue(any(item["can_enter"] for item in data["items"]))


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


if __name__ == "__main__":
    unittest.main()

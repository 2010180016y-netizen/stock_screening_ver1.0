from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vcb_alt.config import AppConfig
from vcb_alt.errors import NotFoundError, ValidationError
from vcb_alt.models import StockSnapshot
from vcb_alt.providers import get_snapshot, provider_status


def make_config(root: Path, provider: str = "manual") -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider=provider,
        external_api_enabled=False,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
    )


class ProviderTests(unittest.TestCase):
    def test_manual_provider_reads_csv_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "snapshots.csv").write_text(
                "ticker,company_name,price,revenue_surprise_pct,forward_guidance_raised,source,data_as_of\n"
                "PLTR,Palantir,125.5,25,true,manual,2026-05-16\n",
                encoding="utf-8",
            )
            snapshot = get_snapshot(make_config(root), "pltr")
            self.assertEqual(snapshot.ticker, "PLTR")
            self.assertEqual(snapshot.price, 125.5)
            self.assertTrue(snapshot.forward_guidance_raised)
            self.assertEqual(snapshot.data_as_of, "2026-05-16")

    def test_manual_provider_requires_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(NotFoundError):
                get_snapshot(make_config(Path(tmp)), "PLTR")

    def test_manual_provider_rejects_unknown_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "snapshots.csv").write_text("ticker,bad_column\nPLTR,x\n", encoding="utf-8")
            with self.assertRaises(ValidationError):
                get_snapshot(make_config(root), "PLTR")

    def test_provider_status_does_not_expose_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp), provider="manual")
            status = provider_status(config)
            self.assertEqual(status["provider"], "manual")
            self.assertIn("capabilities", status)
            self.assertNotIn("api_key", str(status).lower())


if __name__ == "__main__":
    unittest.main()


class NoAlpacaCoverageTests(unittest.TestCase):
    """Alpaca is only needed for whole-market intraday ranking, not for data coverage.

    Yahoo supplies the market group; Finnhub supplies fundamentals, catalyst and
    positioning. Together they clear the 60/100 gate that blocks final selection.
    """

    def _snapshot(self) -> StockSnapshot:
        return StockSnapshot(
            ticker="NVDA", company_name="NVIDIA", price=112.0, source="yahoo",
            data_quality="eod-market", trend_template_score=86.0, surge_score=40.0,
            breakout_volume_ratio=2.4,
        )

    def test_market_data_alone_is_below_the_selection_gate(self) -> None:
        from vcb_alt.scoring import assess_data_coverage, evaluate_snapshot

        snapshot = self._snapshot()
        self.assertLess(int(assess_data_coverage(snapshot)["score"]), 60)
        self.assertFalse(evaluate_snapshot(snapshot).can_enter)

    def test_finnhub_enrichment_clears_the_gate_without_alpaca(self) -> None:
        from unittest.mock import patch

        from vcb_alt import providers as providers_module
        from vcb_alt.scoring import assess_data_coverage, evaluate_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                database_url="sqlite:///./data/test.db", log_level="INFO", timezone="Asia/Seoul",
                data_provider="yahoo", external_api_enabled=True, root_dir=root,
                data_dir=root / "data", log_dir=root / "logs",
                research_data_provider="finnhub", finnhub_api_key="test-key",
                intraday_data_provider="none",
            )
            finnhub_values = {
                "market_cap_m": 2_500_000, "eps_revision_pct": 12, "analyst_revision_score": 40,
                "news_catalyst_30d": True, "news_headline_count_30d": 14,
                "short_interest_pct": 2.1, "call_open_interest": 18000, "analyst_buy_count": 45,
            }
            with patch.object(providers_module, "_load_finnhub_enrichment", return_value=finnhub_values):
                enriched = providers_module.apply_research_enrichment(config, self._snapshot())

            self.assertEqual(enriched.enrichment_source, "finnhub")
            self.assertGreaterEqual(int(assess_data_coverage(enriched)["score"]), 60)
            self.assertTrue(evaluate_snapshot(enriched).can_enter)

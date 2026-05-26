from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vcb_alt.config import AppConfig
from vcb_alt.errors import NotFoundError, ValidationError
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

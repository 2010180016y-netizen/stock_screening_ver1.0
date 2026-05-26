from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vcb_alt.cli import main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_cwd = Path.cwd()
        self.old_env = {
            "VCB_ALT_DATABASE_URL": os.environ.get("VCB_ALT_DATABASE_URL"),
            "VCB_ALT_DATA_PROVIDER": os.environ.get("VCB_ALT_DATA_PROVIDER"),
            "VCB_ALT_EXTERNAL_API_ENABLED": os.environ.get("VCB_ALT_EXTERNAL_API_ENABLED"),
            "VCB_ALT_SCAN_MODE": os.environ.get("VCB_ALT_SCAN_MODE"),
        }
        os.chdir(self.root)
        os.environ["VCB_ALT_DATABASE_URL"] = "sqlite:///./data/test.db"
        os.environ["VCB_ALT_DATA_PROVIDER"] = "sample"
        os.environ["VCB_ALT_EXTERNAL_API_ENABLED"] = "false"
        os.environ["VCB_ALT_SCAN_MODE"] = "watchlist"

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(args)
        return code, output.getvalue()

    def test_init_seed_scan_and_admin_logs(self) -> None:
        code, output = self.run_cli(["init-db", "--seed", "--json"])
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertTrue(payload["ok"])

        code, output = self.run_cli(["scan", "--limit", "2", "--json"])
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["data"]["count"], 2)
        self.assertEqual(payload["data"]["state"], "success")

        code, output = self.run_cli(["admin", "logs", "--json"])
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertGreaterEqual(payload["data"]["count"], 1)

    def test_select_returns_three_portfolio_candidates(self) -> None:
        self.run_cli(["init-db", "--seed"])
        code, output = self.run_cli(["select", "--json"])
        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        selected = payload["data"]["selection"]["selected"]
        self.assertEqual(len(selected), 3)
        self.assertLessEqual(payload["data"]["selection"]["total_size_pct"], 75.0)

    def test_missing_db_returns_friendly_error(self) -> None:
        code, output = self.run_cli(["evaluate", "PLTR", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")

    def test_invalid_ticker_returns_validation_error(self) -> None:
        self.run_cli(["init-db"])
        code, output = self.run_cli(["evaluate", "../PLTR", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(output)
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()

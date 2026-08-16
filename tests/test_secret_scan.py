from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from secret_scan import scan_file  # noqa: E402


class SecretScanTests(unittest.TestCase):
    def scan_text(self, text: str, suffix: str = ".md") -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"sample{suffix}"
            path.write_text(text, encoding="utf-8")
            return scan_file(path)

    def test_detects_hosted_query_string_token(self) -> None:
        """This is the exact shape of the token that leaked through documentation."""
        findings = self.scan_text("https://stockscreeningver10.vercel.app/?token=vcb-beta-20260518-4f6b9c2d8a7e")
        self.assertEqual(len(findings), 1)
        self.assertTrue(
            findings[0].endswith(("possible assigned secret", "possible query-string token")),
            findings[0],
        )

    def test_detects_assigned_access_token_and_provider_keys(self) -> None:
        self.assertTrue(self.scan_text("VCB_ALT_WEB_ACCESS_TOKEN=aVeryRealLookingTokenValue99"))
        self.assertTrue(self.scan_text("VCB_ALT_OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345"))
        self.assertTrue(self.scan_text("postgresql://vcbalt:h8Qz2LmPw01x@db.neon.tech/main"))

    def test_ignores_placeholders_fixtures_and_local_demo_values(self) -> None:
        safe_lines = [
            "VCB_ALT_WEB_ACCESS_TOKEN=replace-with-at-least-16-random-characters",
            "VCB_ALT_WEB_ACCESS_TOKEN=<ROTATED-SEE-VERCEL-ENV>",
            "http://127.0.0.1:8765/?token=local-demo-token-123456",
            'handle_api(config, "POST", "/api/admin/run-worker", "worker_token=worker-token-123456", {}, {})',
            "https://finnhub.io/api/v1/stock/metric?token=finnhub-token-value",
            "VCB_ALT_DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require",
        ]
        for line in safe_lines:
            with self.subTest(line=line):
                self.assertEqual(self.scan_text(line), [])

    def test_repository_is_clean(self) -> None:
        """The whole repository must stay free of live-looking secrets."""
        from secret_scan import iter_files

        findings: list[str] = []
        for path in iter_files():
            findings.extend(scan_file(path))
        self.assertEqual(findings, [], f"secret scan findings: {findings}")


if __name__ == "__main__":
    unittest.main()

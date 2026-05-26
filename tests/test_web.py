from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vcb_alt.config import AppConfig
from vcb_alt.db import add_watchlist, connect, init_db
from vcb_alt.performance import benchmark_scoring
from vcb_alt.web import (
    APP_CSS,
    APP_JS,
    DETAIL_HTML,
    DETAIL_JS,
    INDEX_HTML,
    _auth_cookie_headers,
    _dashboard_js,
    _detail_js,
    _is_authorized,
    handle_api,
)


def make_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="sample",
        external_api_enabled=False,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
    )


class WebTests(unittest.TestCase):
    def test_web_api_scan_and_select(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                add_watchlist(conn, ["PLTR", "MSTR", "VST"])

            scan = handle_api(config, "GET", "/api/scan", "", None)
            self.assertTrue(scan.ok)
            self.assertEqual(scan.data["count"], 3)
            self.assertIn("elapsed_ms", scan.data)

            selection = handle_api(config, "GET", "/api/select", "", None)
            self.assertTrue(selection.ok)
            self.assertEqual(len(selection.data["selection"]["selected"]), 3)
            self.assertIn("public_label", selection.data["selection"]["selected"][0])

            provider = handle_api(config, "GET", "/api/provider-status", "", None)
            self.assertTrue(provider.ok)
            self.assertEqual(provider.data["provider"], "sample")

            release = handle_api(config, "GET", "/api/release-status", "", None)
            self.assertTrue(release.ok)
            self.assertEqual(release.data["release_channel"], "operator_trial")
            self.assertTrue(release.data["user_trial_ready"])
            self.assertFalse(release.data["public_launch_ready"])
            self.assertFalse(release.data["configured_data"]["intraday_ready"])

    def test_benchmark_reports_throughput(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            report = benchmark_scoring(config, ["PLTR", "MSTR"], repeat=5)
            self.assertEqual(report["evaluations"], 10)
            self.assertGreater(report["evals_per_second"], 0)

    def test_public_web_mode_accepts_bearer_or_cookie_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig(
                database_url="sqlite:///./data/test.db",
                log_level="INFO",
                timezone="Asia/Seoul",
                data_provider="sample",
                external_api_enabled=False,
                root_dir=Path(tmp),
                data_dir=Path(tmp) / "data",
                log_dir=Path(tmp) / "logs",
                public_web_enabled=True,
                web_access_token="1234567890abcdef",
            )
            self.assertFalse(_is_authorized(_FakeHandler({}), config, ""))
            self.assertTrue(_is_authorized(_FakeHandler({"authorization": "Bearer 1234567890abcdef"}), config, ""))
            self.assertTrue(_is_authorized(_FakeHandler({"cookie": "vcb_alt_token=1234567890abcdef"}), config, ""))
            cookie = _auth_cookie_headers(
                _FakeHandler({"x-forwarded-proto": "https"}),
                config,
                "token=1234567890abcdef",
            )["Set-Cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("Secure", cookie)

    def test_dashboard_exposes_decision_first_regions(self) -> None:
        self.assertIn("Decision-first dashboard", INDEX_HTML)
        self.assertIn('id="actionable-body"', INDEX_HTML)
        self.assertIn('id="excluded-body"', INDEX_HTML)
        self.assertIn('id="detail-modal"', INDEX_HTML)
        self.assertIn('href="/risk-disclosure"', INDEX_HTML)
        self.assertIn("renderSelection", APP_JS)
        self.assertIn("escapeHtml", APP_JS)
        self.assertIn("publicLabel", APP_JS)
        self.assertIn("ensureUserSession", APP_JS)
        self.assertIn("/api/user/scan", APP_JS)
        self.assertIn("/api/user/select", APP_JS)

    def test_ui_has_responsive_and_language_controls(self) -> None:
        self.assertIn('data-lang-option="ko"', INDEX_HTML)
        self.assertIn('data-lang-option="ko"', DETAIL_HTML)
        self.assertIn("Noto Sans KR", APP_CSS)
        self.assertIn("overflow-wrap: anywhere", APP_CSS)
        self.assertIn("td::before", APP_CSS)
        self.assertIn("localStorage.setItem('vcb_lang'", APP_JS)
        self.assertIn("DETAIL_I18N", DETAIL_JS)

    def test_served_javascript_has_valid_korean_i18n_replacements(self) -> None:
        dashboard_js = _dashboard_js()
        detail_js = _detail_js()

        self.assertIn("접근 권한 필요", dashboard_js)
        self.assertIn("개 중 ${actionable.length}개 진입 검토", dashboard_js)
        self.assertIn("우선 검토 후보", dashboard_js)
        self.assertIn("AI/테크 메가트렌드", dashboard_js)
        self.assertIn("종목 분석", detail_js)
        self.assertIn("최근 5년 가격과 거래량", detail_js)
        self.assertIn("장중 시세", detail_js)
        self.assertIn("전문가 합의 분석", detail_js)

    def test_ticker_analysis_api_includes_chart_industry_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            analysis = handle_api(config, "GET", "/api/ticker-analysis", "ticker=PLTR", None)
            self.assertTrue(analysis.ok)
            self.assertEqual(analysis.data["ticker"], "PLTR")
            self.assertIn("industry", analysis.data["profile"])
            self.assertGreaterEqual(len(analysis.data["history"]["points"]), 1000)
            self.assertFalse(analysis.data["history"]["is_realtime"])
            self.assertTrue(analysis.data["evaluation"]["rationale"])
            self.assertIn("trend_template_score", analysis.data["metrics"])
            self.assertIn("ai_summary", analysis.data)
            self.assertEqual(analysis.data["ai_summary"]["provider"], "template")
            self.assertIn("decision support only", " ".join(analysis.data["ai_summary"]["limitations"]))


class _FakeHandler:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.client_address = ("127.0.0.1", 12345)


if __name__ == "__main__":
    unittest.main()

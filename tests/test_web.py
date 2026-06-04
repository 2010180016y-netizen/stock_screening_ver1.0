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
    _should_auto_seed_watchlist,
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

            health = handle_api(config, "GET", "/api/provider-health", "", None)
            self.assertTrue(health.ok)
            self.assertEqual(health.data["final_candidate_policy"], "allow_configured_fallbacks")
            self.assertIn("alpaca", health.data["providers"])

            diagnostics = handle_api(config, "GET", "/api/provider-diagnostics/alpaca", "", None)
            self.assertTrue(diagnostics.ok)
            self.assertFalse(diagnostics.data["ready"])
            self.assertEqual(diagnostics.data["classification"], "missing_config")

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

    def test_dashboard_exposes_market_wide_discovery_regions(self) -> None:
        self.assertIn("Market-wide discovery", INDEX_HTML)
        self.assertIn("Scan full market / latest candidates", INDEX_HTML)
        self.assertIn("Optional manual research", INDEX_HTML)
        self.assertIn("Secondary drawer", INDEX_HTML)
        self.assertIn("never seed candidate output automatically", INDEX_HTML)
        self.assertIn('id="starter-research-button"', INDEX_HTML)
        self.assertIn('class="panel watchlist-panel secondary-research-panel"', INDEX_HTML)
        self.assertIn('id="scan-freshness"', INDEX_HTML)
        self.assertIn('id="provider-source"', INDEX_HTML)
        self.assertIn('id="coverage-state"', INDEX_HTML)
        self.assertIn('id="fail-closed-state"', INDEX_HTML)
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
        self.assertIn(".discovery-summary", APP_CSS)
        self.assertIn(".primary-cta", APP_CSS)
        self.assertIn(".secondary-research-panel", APP_CSS)
        self.assertIn(".starter-helper", APP_CSS)
        self.assertIn(".candidate-data-row", APP_CSS)
        self.assertIn(".decision-area { order: 1; }", APP_CSS)
        self.assertIn(".sidebar { display: block; border-right: 0; order: 2; }", APP_CSS)
        self.assertIn("overflow-wrap: anywhere", APP_CSS)
        self.assertIn("td::before", APP_CSS)
        self.assertIn("localStorage.setItem('vcb_lang'", APP_JS)
        self.assertIn("DETAIL_I18N", DETAIL_JS)

    def test_served_javascript_has_valid_korean_i18n_replacements(self) -> None:
        dashboard_js = _dashboard_js()
        detail_js = _detail_js()

        self.assertIn("접근 권한 필요", dashboard_js)
        self.assertIn("시장 전체 스캔/최신 후보 확인", dashboard_js)
        self.assertIn("개 중 ${actionable.length}개 연구 후보", dashboard_js)
        self.assertIn("AI/기술 메가트렌드", dashboard_js)
        self.assertIn("실데이터 없으면 후보 미노출", dashboard_js)
        self.assertIn("종목 분석", detail_js)
        self.assertIn("최근 5년 가격과 거래량", detail_js)
        self.assertIn("장중 시세", detail_js)
        self.assertIn("전문가 검토 항목", detail_js)

    def test_watchlist_api_marks_manual_research_as_secondary_in_market_mode(self) -> None:
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
                scan_mode="market_universe",
            )
            with connect(config) as conn:
                init_db(conn)

            watchlist = handle_api(config, "GET", "/api/watchlist", "", None)
            self.assertTrue(watchlist.ok)
            self.assertEqual(watchlist.data["metadata"]["purpose"], "optional_manual_research")
            self.assertEqual(watchlist.data["metadata"]["core_flow"], "market_wide_discovery")
            self.assertFalse(watchlist.data["metadata"]["starter_seeded"])
            self.assertTrue(watchlist.data["metadata"]["starter_helper_available"])
            self.assertIn("scan snapshot endpoint", watchlist.data["metadata"]["result_boundary"])

            add = handle_api(config, "POST", "/api/watchlist", "", {"tickers": "PLTR MSTR"})
            self.assertTrue(add.ok)
            self.assertEqual(add.data["metadata"]["purpose"], "optional_manual_research")

    def test_saas_mode_returns_migration_response_for_legacy_global_endpoints(self) -> None:
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
                user_auth_enabled=True,
                user_registration_enabled=True,
                scan_mode="market_universe",
            )
            with connect(config) as conn:
                init_db(conn)

            cases = [
                ("GET", "/api/watchlist", "/api/user/watchlist"),
                ("POST", "/api/watchlist", "/api/user/watchlist"),
                ("DELETE", "/api/watchlist", "/api/user/watchlist"),
                ("GET", "/api/scan", "/api/user/scan"),
                ("POST", "/api/scan", "/api/user/scan"),
                ("GET", "/api/select", "/api/user/select"),
                ("POST", "/api/select", "/api/user/select"),
            ]
            for method, path, target in cases:
                with self.subTest(method=method, path=path):
                    response = handle_api(config, method, path, "ticker=PLTR", {"tickers": "PLTR"})
                    self.assertFalse(response.ok)
                    self.assertEqual(response.status_code, 410)
                    self.assertEqual(response.error["code"], "LEGACY_ENDPOINT_GONE")
                    self.assertIn(target, response.error["message"])
                    self.assertIn("tenant-scoped /api/user/*", response.error["detail"])

    def test_served_dashboard_uses_tenant_scoped_api_helper_in_saas_mode(self) -> None:
        dashboard_js = _dashboard_js()

        self.assertIn("function endpoint(legacyPath, tenantPath)", dashboard_js)
        self.assertIn("state.config && state.config.user_auth_enabled ? tenantPath : legacyPath", dashboard_js)
        self.assertIn("endpoint('/api/watchlist', '/api/user/watchlist')", dashboard_js)
        self.assertIn("endpoint('/api/scan', '/api/user/scan')", dashboard_js)
        self.assertIn("endpoint('/api/select', '/api/user/select')", dashboard_js)
        self.assertNotIn("api('/api/watchlist'", dashboard_js)
        self.assertNotIn('api("/api/watchlist"', dashboard_js)
        self.assertNotIn("api('/api/scan'", dashboard_js)
        self.assertNotIn('api("/api/scan"', dashboard_js)
        self.assertNotIn("api('/api/select'", dashboard_js)
        self.assertNotIn('api("/api/select"', dashboard_js)

    def test_auto_seed_sample_is_disabled_for_market_wide_and_production_saas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            market_config = AppConfig(
                database_url="sqlite:///./data/test.db",
                log_level="INFO",
                timezone="Asia/Seoul",
                data_provider="sample",
                external_api_enabled=False,
                root_dir=root,
                data_dir=root / "data",
                log_dir=root / "logs",
                auto_seed_sample=True,
                scan_mode="market_universe",
            )
            saas_config = AppConfig(
                **{
                    **market_config.__dict__,
                    "scan_mode": "watchlist",
                    "production_saas_mode": True,
                }
            )
            legacy_config = AppConfig(
                **{
                    **market_config.__dict__,
                    "scan_mode": "watchlist",
                    "production_saas_mode": False,
                }
            )

            self.assertFalse(_should_auto_seed_watchlist(market_config))
            self.assertFalse(_should_auto_seed_watchlist(saas_config))
            self.assertTrue(_should_auto_seed_watchlist(legacy_config))

    def test_served_js_makes_starter_watchlist_optional(self) -> None:
        dashboard_js = _dashboard_js()

        self.assertIn("async function ensureStarterWatchlist() {\n  return;\n}", dashboard_js)
        self.assertIn("async function seedStarterResearchList()", dashboard_js)
        self.assertIn("starter-research-button", dashboard_js)
        self.assertIn("optional_onboarding_helper", dashboard_js)

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
            self.assertEqual(analysis.data["ai_summary"]["provider_label"], "template summary")
            self.assertEqual(analysis.data["ai_summary"]["selection_source"], "deterministic_scoring")
            self.assertEqual(analysis.data["ai_summary"]["role"], "explanation_only")
            self.assertIn("not a trading instruction", " ".join(analysis.data["ai_summary"]["limitations"]))


class _FakeHandler:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.client_address = ("127.0.0.1", 12345)


if __name__ == "__main__":
    unittest.main()

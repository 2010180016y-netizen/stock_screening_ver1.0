from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from vcb_alt.config import AppConfig
from vcb_alt.db import add_watchlist, connect, init_db
from vcb_alt.performance import benchmark_scoring
from vcb_alt.web_auth import (
    TENANT_AUTHENTICATED_PATHS,
    is_tenant_authenticated_path,
    requires_shared_token,
)
from vcb_alt.web import (
    WEB_ASSET_DIR,
    _auth_cookie_headers,
    _client_ip,
    _is_authorized,
    _read_json,
    _should_auto_seed_watchlist,
    _web_asset,
    handle_api,
)


def _served(name: str) -> str:
    """Return exactly what a browser receives for an asset.

    Assertions used to run against the copies embedded in web.py, which the server
    stopped serving once the assets were extracted - so the UI could break while the
    tests stayed green.
    """
    return _web_asset(name)


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

    def test_production_saas_disables_query_access_token_cookie(self) -> None:
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
                production_saas_mode=True,
                allow_query_token_auth=False,
            )
            self.assertFalse(_is_authorized(_FakeHandler({}), config, "token=1234567890abcdef"))
            self.assertTrue(_is_authorized(_FakeHandler({"authorization": "Bearer 1234567890abcdef"}), config, ""))
            self.assertEqual(_auth_cookie_headers(_FakeHandler({}), config, "token=1234567890abcdef"), {})

    def test_provider_panel_endpoints_stay_secret_safe(self) -> None:
        """The operations panel renders these two payloads verbatim.

        They must describe provider state without ever echoing a configured key.
        """
        secret_key = "ak-live-9Zq2Xr7Lp4Tn8Bd1"
        secret_value = "sk-live-3Hv6Wm0Qy5Rc2Jf8"
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **base.__dict__,
                    "external_api_enabled": True,
                    "data_provider": "yahoo",
                    "alpaca_api_key": secret_key,
                    "alpaca_api_secret": secret_value,
                    "finnhub_api_key": secret_value,
                    "openai_api_key": secret_value,
                }
            )
            health = handle_api(config, "GET", "/api/provider-health", "", None)
            self.assertTrue(health.ok)
            self.assertIn("providers", health.data)
            self.assertIn("alpaca", health.data["providers"])
            self.assertIn("status", health.data["providers"]["alpaca"])

            # Stub the probe: with credentials present the endpoint would otherwise make
            # real HTTP calls to Alpaca, which must never happen in a unit test.
            unauthorized = {"ok": False, "status_code": 401, "message": "unauthorized"}
            with patch("vcb_alt.market_universe._probe_alpaca_endpoint", return_value=unauthorized) as probe:
                diagnostics = handle_api(config, "GET", "/api/provider-diagnostics/alpaca", "", None)
            self.assertTrue(probe.called)
            self.assertTrue(diagnostics.ok)
            self.assertFalse(diagnostics.data["ready"])
            self.assertIn("classification", diagnostics.data)
            self.assertIn("next_actions", diagnostics.data)
            # Configured-ness may be reported; the values themselves may not.
            self.assertTrue(diagnostics.data["environment"]["key_configured"])

            for payload in (health.data, diagnostics.data):
                rendered = json.dumps(payload, default=str)
                self.assertNotIn(secret_key, rendered)
                self.assertNotIn(secret_value, rendered)

    def test_shared_token_gate_and_tenant_paths_agree(self) -> None:
        """The auth gate and the rate limiter share one list of tenant paths.

        They used to keep separate copies that had to be edited together; adding a path
        to one and not the other would either expose it or misprice its rate limit.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config(Path(tmp))
            public = AppConfig(
                **{
                    **base.__dict__,
                    "public_web_enabled": True,
                    "web_access_token": "1234567890abcdef",
                    "user_auth_enabled": True,
                }
            )
            for path in sorted(TENANT_AUTHENTICATED_PATHS):
                with self.subTest(path=path):
                    self.assertTrue(is_tenant_authenticated_path(path))
                    self.assertFalse(requires_shared_token(path, public))

            for path in ("/api/health", "/api/auth/register", "/api/auth/login", "/api/admin/run-worker"):
                with self.subTest(path=path):
                    self.assertFalse(requires_shared_token(path, public))

            self.assertTrue(requires_shared_token("/api/provider-status", public))
            self.assertTrue(is_tenant_authenticated_path("/api/jobs/market-scan/abc"))
            self.assertFalse(is_tenant_authenticated_path("/api/provider-status"))

            no_public = AppConfig(**{**base.__dict__, "public_web_enabled": False})
            self.assertFalse(requires_shared_token("/api/provider-status", no_public))

    def test_dashboard_exposes_market_wide_discovery_regions(self) -> None:
        index_html = _served("index.html")
        app_js = _served("app.js")
        self.assertIn("Market-wide discovery", index_html)
        self.assertIn("Scan full market / latest candidates", index_html)
        self.assertIn("Optional manual research", index_html)
        self.assertIn("Secondary drawer", index_html)
        self.assertIn("never seed candidate output automatically", index_html)
        self.assertIn('id="starter-research-button"', index_html)
        self.assertIn('class="panel watchlist-panel secondary-research-panel"', index_html)
        self.assertIn('id="scan-freshness"', index_html)
        self.assertIn('id="provider-source"', index_html)
        self.assertIn('id="coverage-state"', index_html)
        self.assertIn('id="fail-closed-state"', index_html)
        self.assertIn('id="actionable-body"', index_html)
        self.assertIn('id="excluded-body"', index_html)
        # Candidate rows navigate to /ticker/{symbol}; the old in-page modal was
        # unreachable dead markup and was removed.
        self.assertNotIn('id="detail-modal"', index_html)
        self.assertIn('role="status"', index_html)
        self.assertIn(':focus-visible', _served("app.css"))
        self.assertIn('href="/risk-disclosure"', index_html)
        self.assertIn("renderSelection", app_js)
        self.assertIn("escapeHtml", app_js)
        self.assertIn("publicLabel", app_js)
        self.assertIn("ensureUserSession", app_js)
        self.assertIn("/api/user/scan", app_js)
        self.assertIn("/api/user/select", app_js)

    def test_ui_has_responsive_and_language_controls(self) -> None:
        app_css = _served("app.css")
        self.assertIn('data-lang-option="ko"', _served("index.html"))
        self.assertIn('data-lang-option="ko"', _served("detail.html"))
        self.assertIn("Noto Sans KR", app_css)
        self.assertIn(".discovery-summary", app_css)
        self.assertIn(".primary-cta", app_css)
        self.assertIn(".secondary-research-panel", app_css)
        self.assertIn(".starter-helper", app_css)
        self.assertIn(".candidate-data-row", app_css)
        self.assertIn(".decision-area { order: 1; }", app_css)
        self.assertIn(".sidebar { display: block; border-right: 0; order: 2; }", app_css)
        self.assertIn("overflow-wrap: anywhere", app_css)
        self.assertIn("td::before", app_css)
        self.assertIn("localStorage.setItem('vcb_lang'", _served("app.js"))
        self.assertIn("DETAIL_I18N", _served("detail.js"))

    def test_served_javascript_has_valid_korean_i18n_replacements(self) -> None:
        dashboard_js = _served("app.js")
        detail_js = _served("detail.js")

        self.assertIn('접근 권한 필요', dashboard_js)
        self.assertIn('시장 전체 스캔/최신 후보 확인', dashboard_js)
        self.assertIn('${items.length}개 중 ${actionable.length}개 연구 후보', dashboard_js)
        self.assertIn('AI/기술 메가트렌드', dashboard_js)
        self.assertIn('실데이터 없으면 후보 미노출', dashboard_js)
        self.assertIn('종목 분석', detail_js)
        self.assertIn('최근 5년 가격과 거래량', detail_js)
        self.assertIn('장중 시세', detail_js)
        self.assertIn('전문가 검토 항목', detail_js)
        self.assertFalse(_has_mojibake_cjk(dashboard_js))
        self.assertFalse(_has_mojibake_cjk(detail_js))

    def test_extracted_web_assets_are_utf8_and_used(self) -> None:
        expected_assets = {
            "login.html",
            "index.html",
            "detail.html",
            "terms.html",
            "privacy.html",
            "risk-disclosure.html",
            "app.css",
            "app.js",
            "detail.js",
        }
        for name in expected_assets:
            with self.subTest(asset=name):
                self.assertTrue((WEB_ASSET_DIR / name).exists())
                text = _web_asset(name)
                self.assertTrue(text)
                self.assertNotIn("\ufffd", text)

        self.assertIn("\uc2dc\uc7a5 \uc804\uccb4 \uc2a4\uce94/\ucd5c\uc2e0 \ud6c4\ubcf4 \ud655\uc778", _web_asset("app.js"))
        self.assertIn("\uc885\ubaa9 \ubd84\uc11d", _web_asset("detail.js"))
        self.assertIn("Market-wide stock discovery", _web_asset("index.html"))

    def test_client_ip_trusts_forwarded_for_only_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = make_config(Path(tmp))
            handler = _FakeHandler({"x-forwarded-for": "198.51.100.7, 10.0.0.1"}, client_ip="203.0.113.9")
            self.assertEqual(_client_ip(handler, base), "203.0.113.9")
            trusted = AppConfig(**{**base.__dict__, "trusted_proxy_headers": True})
            self.assertEqual(_client_ip(handler, trusted), "198.51.100.7")

    def test_read_json_rejects_invalid_or_oversized_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig(**{**make_config(Path(tmp)).__dict__, "max_json_body_bytes": 8})
            with self.assertRaises(Exception):
                _read_json(_JsonHandler(b"not-json"), config)
            with self.assertRaises(Exception):
                _read_json(_JsonHandler(b'{"long": true}'), config)
            valid = _read_json(_JsonHandler(b'{"a":1}'), AppConfig(**{**config.__dict__, "max_json_body_bytes": 32}))
            self.assertEqual(valid, {"a": 1})

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
        dashboard_js = _served("app.js")

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
        dashboard_js = _served("app.js")

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


def _has_mojibake_cjk(value: str) -> bool:
    if "\ufffd" in value:
        return True
    return any(
        (0x3400 <= ord(ch) <= 0x4DBF)
        or (0x4E00 <= ord(ch) <= 0x9FFF)
        or (0xF900 <= ord(ch) <= 0xFAFF)
        for ch in value
    )


class _FakeHandler:
    def __init__(self, headers: dict[str, str], client_ip: str = "127.0.0.1") -> None:
        self.headers = headers
        self.client_address = (client_ip, 12345)


class _JsonHandler:
    def __init__(self, body: bytes) -> None:
        self.headers = {"content-length": str(len(body))}
        self.rfile = BytesIO(body)


if __name__ == "__main__":
    unittest.main()

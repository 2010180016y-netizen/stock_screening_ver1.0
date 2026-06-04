from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from vcb_alt.ai_summary import build_ai_summary
from vcb_alt.config import AppConfig
from vcb_alt.db import connect, init_db, recent_provider_alerts, record_provider_alert
from vcb_alt.errors import NotFoundError
from vcb_alt.market_universe import _load_alpaca_snapshot_batch
from vcb_alt.provider_resilience import (
    ProviderFailure,
    provider_health_report,
    provider_request_json,
    provider_request_text,
    reset_provider_resilience_state,
)
from vcb_alt.providers import _fetch_yahoo_chart_json


def make_config(root: Path, **overrides: object) -> AppConfig:
    values = {
        "database_url": "sqlite:///./data/test.db",
        "log_level": "INFO",
        "timezone": "Asia/Seoul",
        "data_provider": "yahoo",
        "external_api_enabled": True,
        "root_dir": root,
        "data_dir": root / "data",
        "log_dir": root / "logs",
        "provider_retry_attempts": 1,
        "provider_retry_backoff_seconds": 0.0,
        "provider_circuit_failure_threshold": 10,
        "alpaca_api_key": "alpaca-key-id",
        "alpaca_api_secret": "alpaca-secret-value",
        "finnhub_api_key": "finnhub-token-value",
        "research_data_provider": "finnhub",
        "openai_api_key": "sk-test-openai-secret-value",
        "ai_summary_provider": "openai",
    }
    values.update(overrides)
    return AppConfig(**values)


class ProviderResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_provider_resilience_state()

    def test_alpaca_401_429_timeout_and_malformed_json_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            request = urllib.request.Request("https://data.alpaca.markets/v2/stocks/snapshots")

            with patch(
                "vcb_alt.provider_resilience.urllib.request.urlopen",
                side_effect=_http_error(401, b'{"message":"bad key"}'),
            ):
                with self.assertRaises(ProviderFailure) as auth_error:
                    provider_request_text(config, "alpaca", request)
            self.assertEqual(auth_error.exception.code, "PROVIDER_AUTH_FAILED")
            self.assertNotIn("alpaca-secret-value", json.dumps(auth_error.exception.to_alert()))

            with patch(
                "vcb_alt.provider_resilience.urllib.request.urlopen",
                side_effect=_http_error(429, b'{"message":"too many requests"}'),
            ):
                with self.assertRaises(ProviderFailure) as rate_error:
                    provider_request_text(config, "alpaca", request)
            self.assertEqual(rate_error.exception.code, "PROVIDER_RATE_LIMITED")

            with patch("vcb_alt.provider_resilience.urllib.request.urlopen", side_effect=TimeoutError):
                with self.assertRaises(ProviderFailure) as timeout_error:
                    provider_request_text(config, "alpaca", request)
            self.assertEqual(timeout_error.exception.code, "PROVIDER_TIMEOUT")

            with patch("vcb_alt.provider_resilience.urllib.request.urlopen", return_value=_FakeResponse(b"{bad json")):
                with self.assertRaises(ProviderFailure) as malformed:
                    _load_alpaca_snapshot_batch(config, ["AAPL"])
            self.assertEqual(malformed.exception.code, "PROVIDER_MALFORMED_JSON")

    def test_finnhub_quota_exhausted_is_classified_without_secret_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            request = urllib.request.Request("https://finnhub.io/api/v1/stock/metric?token=finnhub-token-value")
            payload = b'{"error":"API limit reached. Please upgrade your plan."}'

            with patch("vcb_alt.provider_resilience.urllib.request.urlopen", return_value=_FakeResponse(payload)):
                with self.assertRaises(ProviderFailure) as quota:
                    provider_request_json(config, "finnhub", request)

            rendered = json.dumps(quota.exception.to_alert())
            self.assertEqual(quota.exception.code, "PROVIDER_BUDGET_EXHAUSTED")
            self.assertNotIn("finnhub-token-value", rendered)

    def test_yahoo_outage_raises_provider_aware_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp), provider_retry_attempts=1)

            with patch(
                "vcb_alt.provider_resilience.urllib.request.urlopen",
                side_effect=urllib.error.URLError("provider down"),
            ):
                with self.assertRaises(NotFoundError) as yahoo_error:
                    _fetch_yahoo_chart_json("AAPL", 1.0, "1y", config)

            self.assertIn("Yahoo", yahoo_error.exception.message)
            self.assertIn("provider down", yahoo_error.exception.message)

    def test_openai_timeout_falls_back_to_template_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp), provider_retry_attempts=1)

            with patch("vcb_alt.provider_resilience.urllib.request.urlopen", side_effect=TimeoutError):
                summary = build_ai_summary(config, _analysis_payload())

            rendered = json.dumps(summary)
            self.assertEqual(summary["provider"], "template-fallback")
            self.assertEqual(summary["provider_label"], "template summary fallback")
            self.assertEqual(summary["selection_source"], "deterministic_scoring")
            self.assertEqual(summary["role"], "explanation_only")
            self.assertIn("OpenAI explanation-summary generation failed", " ".join(summary["limitations"]))
            self.assertNotIn("sk-test-openai-secret-value", rendered)

    def test_provider_health_and_alert_events_redact_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp), provider_alpaca_daily_budget=1)
            request = urllib.request.Request("https://data.alpaca.markets/v2/stocks/snapshots")
            with patch("vcb_alt.provider_resilience.urllib.request.urlopen", return_value=_FakeResponse(b"{}")):
                provider_request_json(config, "alpaca", request)

            health = provider_health_report(config)
            self.assertEqual(health["providers"]["alpaca"]["budget"]["remaining"], 0)
            self.assertNotIn("alpaca-secret-value", json.dumps(health))

            with connect(config) as conn:
                init_db(conn)
                record_provider_alert(
                    conn,
                    "alpaca",
                    "fixture",
                    "critical",
                    "PROVIDER_AUTH_FAILED",
                    "secret should be removed sk-test-openai-secret-value",
                    recovery="rotate alpaca-secret-value",
                    metadata={"api_key": "alpaca-key-id", "token": "finnhub-token-value"},
                )
                alerts = recent_provider_alerts(conn, 5)

            rendered_alerts = json.dumps(alerts)
            self.assertIn("[REDACTED]", rendered_alerts)
            self.assertNotIn("alpaca-key-id", rendered_alerts)
            self.assertNotIn("finnhub-token-value", rendered_alerts)
            self.assertNotIn("sk-test-openai-secret-value", rendered_alerts)


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://provider.invalid",
        code,
        "provider error",
        hdrs={},
        fp=io.BytesIO(body),
    )


class _FakeResponse:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _analysis_payload() -> dict[str, object]:
    return {
        "ticker": "AAPL",
        "profile": {"sector": "Technology", "industry": "Consumer Electronics"},
        "history": {"realtime_note": "EOD data"},
        "metrics": {"return_12w_pct": 5},
        "evaluation": {
            "combined_score": 61,
            "public_label": "Review candidate",
            "primary_archetype_label": "Technical Momentum",
            "rationale": ["Composite score is above threshold."],
            "warnings": [],
            "data_coverage_score": 60,
            "data_coverage_label": "enriched",
            "data_coverage_detail": "fixture",
            "source": "fixture",
            "data_as_of": "2026-06-03",
        },
    }


if __name__ == "__main__":
    unittest.main()

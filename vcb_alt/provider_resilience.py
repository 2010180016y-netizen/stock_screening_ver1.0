from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .errors import AppError
from .security import redact_dict, redact_text


PROVIDER_NAMES = ("alpaca", "finnhub", "yahoo", "sec", "openai", "template")

FALLBACK_POLICIES = {
    "alpaca": "fail_closed_when_live_data_required",
    "finnhub": "degrade_to_csv_or_missing_enrichment",
    "yahoo": "fail_closed_for_live_candidates_or_use_cached_eod_when_fresh",
    "sec": "degrade_to_missing_filing_metadata",
    "openai": "fallback_to_template_summary",
    "template": "always_available_local_summary",
}

RECOVERY_GUIDANCE = {
    "PROVIDER_AUTH_FAILED": "Rotate/regenerate the provider credentials, verify account context and feed permissions, then redeploy.",
    "PROVIDER_RATE_LIMITED": "Wait for the provider rate-limit window or reduce worker frequency/batch size.",
    "PROVIDER_BUDGET_EXHAUSTED": "Increase the configured provider budget or wait for the daily budget window to reset.",
    "PROVIDER_TIMEOUT": "Check provider status and network path; increase timeout only after queue latency is acceptable.",
    "PROVIDER_NETWORK_ERROR": "Check provider status, DNS/network egress, and serverless outbound access.",
    "PROVIDER_MALFORMED_JSON": "Treat the provider response as unavailable; keep live candidate output blocked until valid JSON returns.",
    "PROVIDER_CIRCUIT_OPEN": "Wait for the circuit reset window or manually verify the provider before resuming worker scans.",
}


@dataclass
class ProviderFailure(AppError):
    provider: str = "unknown"
    retryable: bool = False
    recovery: str = ""
    status_code: int = 503
    code: str = "PROVIDER_FAILURE"

    def __init__(
        self,
        provider: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int = 503,
        detail: str | None = None,
        recovery: str | None = None,
    ) -> None:
        raw_recovery = recovery or RECOVERY_GUIDANCE.get(
            code,
            "Check the provider configuration and retry after verification.",
        )
        resolved_recovery = redact_text(raw_recovery)
        detail_parts = []
        if detail:
            detail_parts.append(redact_text(detail))
        if resolved_recovery:
            detail_parts.append(f"Recovery: {resolved_recovery}")
        super().__init__(redact_text(message), detail=" ".join(detail_parts) or None)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.recovery = resolved_recovery

    def to_alert(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "recovery": self.recovery,
        }


@dataclass
class _ProviderState:
    provider: str
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0
    budget_used: int = 0
    budget_window_started_at: float = field(default_factory=time.time)
    total_requests: int = 0
    total_failures: int = 0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_status_code: int | None = None


_STATE_LOCK = threading.Lock()
_PROVIDER_STATE: dict[str, _ProviderState] = {name: _ProviderState(name) for name in PROVIDER_NAMES}


def provider_request_text(
    config: AppConfig,
    provider: str,
    request: urllib.request.Request,
    *,
    timeout_seconds: float | None = None,
    retry_statuses: set[int] | None = None,
) -> str:
    provider_name = _normalize_provider(provider)
    attempts = max(1, int(getattr(config, "provider_retry_attempts", 2)))
    retry_statuses = retry_statuses or {429, 500, 502, 503, 504}
    last_failure: ProviderFailure | None = None

    for attempt in range(1, attempts + 1):
        _guard_provider(config, provider_name)
        _consume_budget(config, provider_name)
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or float(config.market_data_timeout_seconds),
            ) as response:
                body = response.read().decode("utf-8")
            _mark_success(provider_name)
            return body
        except urllib.error.HTTPError as exc:
            failure = _failure_from_http_error(provider_name, exc, retryable_statuses=retry_statuses)
        except TimeoutError:
            failure = ProviderFailure(
                provider_name,
                "PROVIDER_TIMEOUT",
                f"{provider_name} request timed out.",
                retryable=True,
                status_code=504,
            )
        except urllib.error.URLError as exc:
            reason = redact_text(str(getattr(exc, "reason", exc)))
            failure = ProviderFailure(
                provider_name,
                "PROVIDER_NETWORK_ERROR",
                f"{provider_name} network error: {reason}",
                retryable=True,
                status_code=503,
            )
        _mark_failure(config, failure)
        last_failure = failure
        if not failure.retryable or attempt >= attempts:
            raise failure
        _sleep_before_retry(config, attempt)

    if last_failure is not None:
        raise last_failure
    raise ProviderFailure(provider_name, "PROVIDER_FAILURE", f"{provider_name} request failed.")


def provider_request_json(
    config: AppConfig,
    provider: str,
    request: urllib.request.Request,
    *,
    timeout_seconds: float | None = None,
    retry_statuses: set[int] | None = None,
) -> Any:
    provider_name = _normalize_provider(provider)
    body = provider_request_text(
        config,
        provider_name,
        request,
        timeout_seconds=timeout_seconds,
        retry_statuses=retry_statuses,
    )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        failure = ProviderFailure(
            provider_name,
            "PROVIDER_MALFORMED_JSON",
            f"{provider_name} response could not be parsed as JSON.",
            retryable=False,
            status_code=502,
            detail=str(exc),
        )
        _mark_failure(config, failure)
        raise failure from exc
    quota_failure = _quota_failure_from_payload(provider_name, payload)
    if quota_failure is not None:
        _mark_failure(config, quota_failure)
        raise quota_failure
    return payload


def provider_health_report(config: AppConfig) -> dict[str, Any]:
    now = time.time()
    with _STATE_LOCK:
        providers = {
            name: _provider_health(config, state, now)
            for name, state in sorted(_PROVIDER_STATE.items())
        }
    return {
        "live_data_required": config.market_scan_requires_live_data,
        "production_saas_mode": config.production_saas_mode,
        "final_candidate_policy": (
            "fail_closed" if config.market_scan_requires_live_data else "allow_configured_fallbacks"
        ),
        "timeout_seconds": config.market_data_timeout_seconds,
        "retry_attempts": config.provider_retry_attempts,
        "retry_backoff_seconds": config.provider_retry_backoff_seconds,
        "circuit_failure_threshold": config.provider_circuit_failure_threshold,
        "circuit_reset_seconds": config.provider_circuit_reset_seconds,
        "providers": providers,
        "alerts_endpoint": "/api/admin/provider-alerts",
    }


def reset_provider_resilience_state() -> None:
    with _STATE_LOCK:
        _PROVIDER_STATE.clear()
        _PROVIDER_STATE.update({name: _ProviderState(name) for name in PROVIDER_NAMES})


def provider_alert_payload(exc: BaseException, *, context: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if isinstance(exc, ProviderFailure):
        return {
            "provider": exc.provider,
            "event_type": context,
            "severity": _alert_severity(exc),
            "code": exc.code,
            "message": exc.message,
            "recovery": exc.recovery,
            "metadata": redact_dict({**(metadata or {}), "retryable": exc.retryable, "status_code": exc.status_code}),
        }
    if isinstance(exc, AppError) and _looks_like_provider_error(exc.message):
        provider = _provider_from_message(exc.message)
        return {
            "provider": provider,
            "event_type": context,
            "severity": "critical",
            "code": exc.code,
            "message": redact_text(exc.message),
            "recovery": "Review provider credentials, quota, feed permission, and worker logs before retrying.",
            "metadata": redact_dict(metadata or {}),
        }
    return None


def _normalize_provider(provider: str) -> str:
    value = str(provider or "").lower().strip()
    return value if value in PROVIDER_NAMES else "unknown"


def _guard_provider(config: AppConfig, provider: str) -> None:
    now = time.time()
    with _STATE_LOCK:
        state = _PROVIDER_STATE.setdefault(provider, _ProviderState(provider))
        _reset_budget_if_needed(state, now)
        if state.circuit_open_until > now:
            until = datetime.fromtimestamp(state.circuit_open_until, timezone.utc).isoformat()
            raise ProviderFailure(
                provider,
                "PROVIDER_CIRCUIT_OPEN",
                f"{provider} circuit breaker is open until {until}.",
                retryable=False,
                status_code=503,
            )


def _consume_budget(config: AppConfig, provider: str) -> None:
    now = time.time()
    budget = _provider_budget(config, provider)
    with _STATE_LOCK:
        state = _PROVIDER_STATE.setdefault(provider, _ProviderState(provider))
        _reset_budget_if_needed(state, now)
        if state.budget_used >= budget:
            raise ProviderFailure(
                provider,
                "PROVIDER_BUDGET_EXHAUSTED",
                f"{provider} daily request budget is exhausted.",
                retryable=False,
                status_code=429,
            )
        state.budget_used += 1
        state.total_requests += 1


def _mark_success(provider: str) -> None:
    with _STATE_LOCK:
        state = _PROVIDER_STATE.setdefault(provider, _ProviderState(provider))
        state.consecutive_failures = 0
        state.circuit_open_until = 0.0
        state.last_success_at = _utc_iso()


def _mark_failure(config: AppConfig, failure: ProviderFailure) -> None:
    with _STATE_LOCK:
        state = _PROVIDER_STATE.setdefault(failure.provider, _ProviderState(failure.provider))
        state.consecutive_failures += 1
        state.total_failures += 1
        state.last_failure_at = _utc_iso()
        state.last_error_code = failure.code
        state.last_error_message = failure.message
        state.last_status_code = failure.status_code
        threshold = max(1, int(getattr(config, "provider_circuit_failure_threshold", 3)))
        if state.consecutive_failures >= threshold or failure.code in {"PROVIDER_BUDGET_EXHAUSTED"}:
            state.circuit_open_until = time.time() + max(1, int(getattr(config, "provider_circuit_reset_seconds", 300)))


def _sleep_before_retry(config: AppConfig, attempt: int) -> None:
    backoff = max(0.0, float(getattr(config, "provider_retry_backoff_seconds", 0.05)))
    if backoff:
        time.sleep(min(2.0, backoff * attempt))


def _failure_from_http_error(
    provider: str,
    exc: urllib.error.HTTPError,
    *,
    retryable_statuses: set[int],
) -> ProviderFailure:
    body = _safe_http_body(exc)
    if exc.code in {401, 403}:
        return ProviderFailure(
            provider,
            "PROVIDER_AUTH_FAILED",
            f"{provider} rejected the request with HTTP {exc.code}. Check credentials, account context, and feed permissions.",
            retryable=False,
            status_code=503,
            detail=f"Provider HTTP {exc.code}. {body}".strip(),
        )
    if exc.code == 429:
        return ProviderFailure(
            provider,
            "PROVIDER_RATE_LIMITED",
            f"{provider} rate limit reached.",
            retryable=True,
            status_code=429,
            detail=body,
        )
    retryable = exc.code in retryable_statuses
    return ProviderFailure(
        provider,
        "PROVIDER_HTTP_ERROR",
        f"{provider} request failed with HTTP {exc.code}.",
        retryable=retryable,
        status_code=exc.code,
        detail=body,
        recovery="Check provider status and request parameters before retrying.",
    )


def _safe_http_body(exc: urllib.error.HTTPError) -> str:
    try:
        return redact_text(exc.read().decode("utf-8")[:240])
    except Exception:
        return ""


def _quota_failure_from_payload(provider: str, payload: Any) -> ProviderFailure | None:
    if provider != "finnhub":
        return None
    text = ""
    if isinstance(payload, dict):
        text = " ".join(str(payload.get(key, "")) for key in ("error", "message", "detail"))
    if not text:
        return None
    lowered = text.lower()
    if "limit" in lowered or "quota" in lowered or "exhausted" in lowered:
        return ProviderFailure(
            provider,
            "PROVIDER_BUDGET_EXHAUSTED",
            "Finnhub quota appears exhausted for the current window.",
            retryable=False,
            status_code=429,
            detail=text,
            recovery="Reduce Finnhub enrichment calls, wait for quota reset, or upgrade the Finnhub plan before worker scans resume.",
        )
    return None


def _provider_health(config: AppConfig, state: _ProviderState, now: float) -> dict[str, Any]:
    configured = _provider_configured(config, state.provider)
    circuit_open = state.circuit_open_until > now
    budget = _provider_budget(config, state.provider)
    budget_remaining = max(0, budget - state.budget_used)
    if not configured:
        status = "not_configured"
    elif circuit_open:
        status = "circuit_open"
    elif budget_remaining <= 0:
        status = "budget_exhausted"
    elif state.last_error_code:
        status = "degraded"
    else:
        status = "ready"
    return {
        "configured": configured,
        "status": status,
        "fallback_policy": FALLBACK_POLICIES.get(state.provider, "fail_closed"),
        "budget": {
            "daily_limit": budget,
            "used": state.budget_used,
            "remaining": budget_remaining,
            "window_started_at": datetime.fromtimestamp(state.budget_window_started_at, timezone.utc).isoformat(),
        },
        "circuit": {
            "open": circuit_open,
            "open_until": (
                datetime.fromtimestamp(state.circuit_open_until, timezone.utc).isoformat()
                if circuit_open
                else None
            ),
            "consecutive_failures": state.consecutive_failures,
        },
        "last_success_at": state.last_success_at,
        "last_failure_at": state.last_failure_at,
        "last_error_code": state.last_error_code,
        "last_error_message": state.last_error_message,
        "last_status_code": state.last_status_code,
        "total_requests": state.total_requests,
        "total_failures": state.total_failures,
    }


def _provider_configured(config: AppConfig, provider: str) -> bool:
    if provider == "alpaca":
        return bool(config.external_api_enabled and config.alpaca_api_key and config.alpaca_api_secret)
    if provider == "finnhub":
        return bool(config.research_data_provider.startswith("finnhub") and config.finnhub_api_key)
    if provider == "yahoo":
        return bool(config.external_api_enabled and config.data_provider in {"yahoo", "yahoo_chart"})
    if provider == "sec":
        return bool(config.sec_company_facts_enabled and config.sec_user_agent)
    if provider == "openai":
        return bool(config.ai_summary_provider == "openai" and config.openai_api_key)
    if provider == "template":
        return True
    return False


def _provider_budget(config: AppConfig, provider: str) -> int:
    mapping = {
        "alpaca": "provider_alpaca_daily_budget",
        "finnhub": "provider_finnhub_daily_budget",
        "yahoo": "provider_yahoo_daily_budget",
        "sec": "provider_sec_daily_budget",
        "openai": "provider_openai_daily_budget",
        "template": "provider_template_daily_budget",
    }
    return max(1, int(getattr(config, mapping.get(provider, ""), 1000)))


def _reset_budget_if_needed(state: _ProviderState, now: float) -> None:
    if now - state.budget_window_started_at >= 86400:
        state.budget_window_started_at = now
        state.budget_used = 0


def _alert_severity(exc: ProviderFailure) -> str:
    if exc.code in {"PROVIDER_AUTH_FAILED", "PROVIDER_BUDGET_EXHAUSTED", "PROVIDER_CIRCUIT_OPEN"}:
        return "critical"
    if exc.code in {"PROVIDER_RATE_LIMITED", "PROVIDER_TIMEOUT", "PROVIDER_MALFORMED_JSON"}:
        return "warning"
    return "info" if exc.retryable else "warning"


def _looks_like_provider_error(message: str) -> bool:
    lowered = message.lower()
    return any(name in lowered for name in ("alpaca", "finnhub", "yahoo", "sec", "openai"))


def _provider_from_message(message: str) -> str:
    lowered = message.lower()
    for name in ("alpaca", "finnhub", "yahoo", "sec", "openai"):
        if name in lowered:
            return name
    return "unknown"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

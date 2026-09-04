from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ValidationError

# SHA-256 of credentials known to be publicly exposed. Storing the digest rather than the
# value keeps the secret out of the repository while still letting the app refuse to boot
# if a leaked credential is configured again. Add an entry whenever a secret is burned.
REVOKED_SECRET_HASHES = frozenset(
    {
        # Operator-trial VCB_ALT_WEB_ACCESS_TOKEN, committed in plain text alongside the
        # live deployment URL until 2026-08-17.
        "a66ac56bcfb714a83477aa0813fb23eced35209f2adb18d24d98d44da5bbabb6",
    }
)


def _is_revoked_secret(value: str) -> bool:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() in REVOKED_SECRET_HASHES


# Ceiling on concurrent provider requests. The scan is network-bound, so concurrency is
# what makes it fast, but the market data endpoints are free and unauthenticated: past a
# certain width this stops being a speed-up and becomes something a provider throttles or
# blocks. Sixteen keeps a 150-symbol sweep inside a serverless execution limit with room
# to spare.
MAX_PROVIDER_FETCH_WORKERS = 16


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    log_level: str
    timezone: str
    data_provider: str
    external_api_enabled: bool
    root_dir: Path
    data_dir: Path
    log_dir: Path
    database_backend: str = "sqlite"
    public_web_enabled: bool = False
    web_access_token: str = ""
    auto_seed_sample: bool = True
    market_data_timeout_seconds: float = 10.0
    market_data_cache_ttl_hours: float = 12.0
    provider_retry_attempts: int = 2
    provider_retry_backoff_seconds: float = 0.05
    provider_circuit_failure_threshold: int = 3
    provider_circuit_reset_seconds: int = 300
    provider_alpaca_daily_budget: int = 2500
    provider_finnhub_daily_budget: int = 500
    provider_yahoo_daily_budget: int = 2500
    provider_sec_daily_budget: int = 500
    provider_openai_daily_budget: int = 200
    provider_template_daily_budget: int = 1000000
    stooq_api_key: str = ""
    intraday_data_provider: str = "none"
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_data_feed: str = "iex"
    intraday_cache_ttl_seconds: float = 60.0
    research_data_provider: str = "csv"
    finnhub_api_key: str = ""
    research_data_cache_ttl_hours: float = 12.0
    sec_company_facts_enabled: bool = False
    sec_user_agent: str = "vcb-alt-stock-screener contact@example.invalid"
    ai_summary_provider: str = "template"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    ai_summary_cache_ttl_hours: float = 12.0
    user_auth_enabled: bool = False
    user_registration_enabled: bool = False
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 2000
    login_rate_limit_per_minute: int = 20
    user_rate_limit_per_minute: int = 600
    worker_rate_limit_per_minute: int = 1200
    rate_limit_backend: str = "memory"
    scan_queue_enabled: bool = False
    worker_token: str = ""
    worker_cron_enabled: bool = False
    production_saas_mode: bool = False
    trusted_proxy_headers: bool = False
    allow_query_token_auth: bool = True
    max_json_body_bytes: int = 65536
    global_operator_emails: tuple[str, ...] = ()
    scan_mode: str = "watchlist"
    market_universe_provider: str = "auto"
    market_universe_max_symbols: int = 5000
    market_prefilter_limit: int = 30
    market_prefilter_provider: str = "auto"
    yahoo_prefilter_max_symbols: int = 150
    prefilter_time_budget_seconds: float = 20.0
    provider_fetch_workers: int = 8
    market_snapshot_batch_size: int = 100
    market_scan_requires_live_data: bool = False

    @property
    def database_path(self) -> str:
        if not self.database_url.startswith("sqlite:///"):
            raise ValidationError("Only sqlite:/// DATABASE_URL values are supported in the local MVP.")
        raw_path = self.database_url.removeprefix("sqlite:///")
        if raw_path == ":memory:":
            return raw_path
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.root_dir / path
        return str(path)


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_dir(root: Path, raw_value: str) -> Path:
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def load_config(root_dir: Path | None = None) -> AppConfig:
    root = (root_dir or Path.cwd()).resolve()
    env_file_values = _load_env_file(root / ".env")

    def get(name: str, default: str) -> str:
        prefixed = f"VCB_ALT_{name}"
        return os.getenv(prefixed) or env_file_values.get(prefixed) or os.getenv(name) or env_file_values.get(name) or default

    database_url = get("DATABASE_URL", "sqlite:///./data/vcb_alt.db")
    database_backend = _database_backend(database_url)
    log_level = get("LOG_LEVEL", "INFO").upper()
    timezone = get("TIMEZONE", "Asia/Seoul")
    data_provider = get("DATA_PROVIDER", "sample").lower()
    external_api_enabled = _truthy(get("EXTERNAL_API_ENABLED", "false"))

    if data_provider not in {"sample", "manual"} and not external_api_enabled:
        raise ValidationError("External data providers require VCB_ALT_EXTERNAL_API_ENABLED=true.")
    public_web_enabled = _truthy(get("PUBLIC_WEB_ENABLED", "false"))
    web_access_token = get("WEB_ACCESS_TOKEN", "")
    if public_web_enabled and len(web_access_token) < 16:
        raise ValidationError("Public web mode requires VCB_ALT_WEB_ACCESS_TOKEN with at least 16 characters.")
    if web_access_token and _is_revoked_secret(web_access_token):
        raise ValidationError(
            "VCB_ALT_WEB_ACCESS_TOKEN matches a credential that was publicly exposed in this "
            "repository's history. Generate a new random token before starting the app."
        )
    market_data_timeout_seconds = _parse_positive_float(get("MARKET_DATA_TIMEOUT_SECONDS", "10"), "MARKET_DATA_TIMEOUT_SECONDS")
    market_data_cache_ttl_hours = _parse_positive_float(get("MARKET_DATA_CACHE_TTL_HOURS", "12"), "MARKET_DATA_CACHE_TTL_HOURS")
    provider_retry_attempts = _parse_positive_int(get("PROVIDER_RETRY_ATTEMPTS", "2"), "PROVIDER_RETRY_ATTEMPTS")
    provider_retry_backoff_seconds = _parse_non_negative_float(
        get("PROVIDER_RETRY_BACKOFF_SECONDS", "0.05"),
        "PROVIDER_RETRY_BACKOFF_SECONDS",
    )
    provider_circuit_failure_threshold = _parse_positive_int(
        get("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "3"),
        "PROVIDER_CIRCUIT_FAILURE_THRESHOLD",
    )
    provider_circuit_reset_seconds = _parse_positive_int(
        get("PROVIDER_CIRCUIT_RESET_SECONDS", "300"),
        "PROVIDER_CIRCUIT_RESET_SECONDS",
    )
    provider_alpaca_daily_budget = _parse_positive_int(
        get("PROVIDER_ALPACA_DAILY_BUDGET", "2500"),
        "PROVIDER_ALPACA_DAILY_BUDGET",
    )
    provider_finnhub_daily_budget = _parse_positive_int(
        get("PROVIDER_FINNHUB_DAILY_BUDGET", "500"),
        "PROVIDER_FINNHUB_DAILY_BUDGET",
    )
    provider_yahoo_daily_budget = _parse_positive_int(
        get("PROVIDER_YAHOO_DAILY_BUDGET", "2500"),
        "PROVIDER_YAHOO_DAILY_BUDGET",
    )
    provider_sec_daily_budget = _parse_positive_int(
        get("PROVIDER_SEC_DAILY_BUDGET", "500"),
        "PROVIDER_SEC_DAILY_BUDGET",
    )
    provider_openai_daily_budget = _parse_positive_int(
        get("PROVIDER_OPENAI_DAILY_BUDGET", "200"),
        "PROVIDER_OPENAI_DAILY_BUDGET",
    )
    provider_template_daily_budget = _parse_positive_int(
        get("PROVIDER_TEMPLATE_DAILY_BUDGET", "1000000"),
        "PROVIDER_TEMPLATE_DAILY_BUDGET",
    )
    stooq_api_key = get("STOOQ_API_KEY", "")
    intraday_data_provider = get("INTRADAY_DATA_PROVIDER", "none").lower()
    if intraday_data_provider not in {"none", "alpaca"}:
        raise ValidationError("INTRADAY_DATA_PROVIDER must be one of: none, alpaca.")
    alpaca_api_key = get("ALPACA_API_KEY", "")
    alpaca_api_secret = get("ALPACA_API_SECRET", "")
    alpaca_data_feed = get("ALPACA_DATA_FEED", "iex").lower()
    if alpaca_data_feed not in {"iex", "sip", "delayed_sip", "otc", "boats", "overnight"}:
        raise ValidationError("ALPACA_DATA_FEED must be one of: iex, sip, delayed_sip, otc, boats, overnight.")
    intraday_cache_ttl_seconds = _parse_positive_float(
        get("INTRADAY_CACHE_TTL_SECONDS", "60"),
        "INTRADAY_CACHE_TTL_SECONDS",
    )
    research_data_provider = get("RESEARCH_DATA_PROVIDER", "csv").lower()
    if research_data_provider not in {"csv", "finnhub", "finnhub_csv"}:
        raise ValidationError("RESEARCH_DATA_PROVIDER must be one of: csv, finnhub, finnhub_csv.")
    finnhub_api_key = get("FINNHUB_API_KEY", "")
    research_data_cache_ttl_hours = _parse_positive_float(
        get("RESEARCH_DATA_CACHE_TTL_HOURS", "12"),
        "RESEARCH_DATA_CACHE_TTL_HOURS",
    )
    sec_company_facts_enabled = _truthy(get("SEC_COMPANY_FACTS_ENABLED", "false"))
    sec_user_agent = get("SEC_USER_AGENT", "vcb-alt-stock-screener contact@example.invalid")
    ai_summary_provider = get("AI_SUMMARY_PROVIDER", "template").lower()
    if ai_summary_provider not in {"template", "openai"}:
        raise ValidationError("AI_SUMMARY_PROVIDER must be one of: template, openai.")
    openai_api_key = get("OPENAI_API_KEY", "")
    openai_model = get("OPENAI_MODEL", "gpt-4.1-mini")
    ai_summary_cache_ttl_hours = _parse_positive_float(
        get("AI_SUMMARY_CACHE_TTL_HOURS", "12"),
        "AI_SUMMARY_CACHE_TTL_HOURS",
    )
    user_auth_enabled = _truthy(get("USER_AUTH_ENABLED", "false"))
    user_registration_enabled = _truthy(get("USER_REGISTRATION_ENABLED", "false"))
    rate_limit_per_minute = _parse_positive_int(get("RATE_LIMIT_PER_MINUTE", "120"), "RATE_LIMIT_PER_MINUTE")
    auth_rate_limit_per_minute = _parse_positive_int(
        get("AUTH_RATE_LIMIT_PER_MINUTE", "2000"),
        "AUTH_RATE_LIMIT_PER_MINUTE",
    )
    login_rate_limit_per_minute = _parse_positive_int(
        get("LOGIN_RATE_LIMIT_PER_MINUTE", "20"),
        "LOGIN_RATE_LIMIT_PER_MINUTE",
    )
    user_rate_limit_per_minute = _parse_positive_int(
        get("USER_RATE_LIMIT_PER_MINUTE", "600"),
        "USER_RATE_LIMIT_PER_MINUTE",
    )
    worker_rate_limit_per_minute = _parse_positive_int(
        get("WORKER_RATE_LIMIT_PER_MINUTE", "1200"),
        "WORKER_RATE_LIMIT_PER_MINUTE",
    )
    rate_limit_backend = get("RATE_LIMIT_BACKEND", "memory").lower()
    if rate_limit_backend not in {"memory", "database"}:
        raise ValidationError("RATE_LIMIT_BACKEND must be one of: memory, database.")
    scan_queue_enabled = _truthy(get("SCAN_QUEUE_ENABLED", "false"))
    worker_token = get("WORKER_TOKEN", "")
    worker_cron_enabled = _truthy(get("WORKER_CRON_ENABLED", "false"))
    production_saas_mode = _truthy(get("PRODUCTION_SAAS_MODE", "false"))
    trusted_proxy_headers = _truthy(get("TRUSTED_PROXY_HEADERS", "false"))
    allow_query_token_auth = _truthy(get("ALLOW_QUERY_TOKEN_AUTH", "true"))
    if production_saas_mode:
        allow_query_token_auth = False
    max_json_body_bytes = _parse_positive_int(get("MAX_JSON_BODY_BYTES", "65536"), "MAX_JSON_BODY_BYTES")
    global_operator_emails = tuple(
        sorted({item.strip().lower() for item in get("GLOBAL_OPERATOR_EMAILS", "").split(",") if item.strip()})
    )
    scan_mode = get("SCAN_MODE", "market_universe").lower()
    if scan_mode not in {"market_universe", "watchlist"}:
        raise ValidationError("SCAN_MODE must be one of: market_universe, watchlist.")
    market_universe_provider = get("MARKET_UNIVERSE_PROVIDER", "auto").lower()
    if market_universe_provider not in {"auto", "alpaca", "csv", "sample", "watchlist"}:
        raise ValidationError("MARKET_UNIVERSE_PROVIDER must be one of: auto, alpaca, csv, watchlist, sample.")
    market_universe_max_symbols = _parse_positive_int(
        get("MARKET_UNIVERSE_MAX_SYMBOLS", "5000"),
        "MARKET_UNIVERSE_MAX_SYMBOLS",
    )
    market_prefilter_limit = _parse_positive_int(
        get("MARKET_PREFILTER_LIMIT", "30"),
        "MARKET_PREFILTER_LIMIT",
    )
    market_prefilter_provider = get("MARKET_PREFILTER_PROVIDER", "auto").lower()
    if market_prefilter_provider not in {"auto", "alpaca", "yahoo", "none"}:
        raise ValidationError("MARKET_PREFILTER_PROVIDER must be one of: auto, alpaca, yahoo, none.")
    yahoo_prefilter_max_symbols = _parse_positive_int(
        get("YAHOO_PREFILTER_MAX_SYMBOLS", "150"),
        "YAHOO_PREFILTER_MAX_SYMBOLS",
    )
    prefilter_time_budget_seconds = _parse_positive_float(
        get("PREFILTER_TIME_BUDGET_SECONDS", "20"),
        "PREFILTER_TIME_BUDGET_SECONDS",
    )
    provider_fetch_workers = _parse_positive_int(
        get("PROVIDER_FETCH_WORKERS", "8"),
        "PROVIDER_FETCH_WORKERS",
    )
    if provider_fetch_workers > MAX_PROVIDER_FETCH_WORKERS:
        raise ValidationError(
            f"PROVIDER_FETCH_WORKERS must not exceed {MAX_PROVIDER_FETCH_WORKERS}; "
            "a higher value is a request flood against a free market data endpoint, not a speed-up."
        )
    market_snapshot_batch_size = _parse_positive_int(
        get("MARKET_SNAPSHOT_BATCH_SIZE", "100"),
        "MARKET_SNAPSHOT_BATCH_SIZE",
    )
    if market_snapshot_batch_size > 500:
        raise ValidationError("MARKET_SNAPSHOT_BATCH_SIZE must be 500 or less.")
    market_scan_requires_live_data = _truthy(get("MARKET_SCAN_REQUIRES_LIVE_DATA", "false"))
    if production_saas_mode:
        _validate_production_saas_mode(
            database_backend=database_backend,
            user_auth_enabled=user_auth_enabled,
            rate_limit_backend=rate_limit_backend,
            scan_queue_enabled=scan_queue_enabled,
            worker_token=worker_token,
            worker_cron_enabled=worker_cron_enabled,
        )
    data_dir = _resolve_dir(root, get("DATA_DIR", "./data"))
    log_dir = _resolve_dir(root, get("LOG_DIR", "./logs"))

    return AppConfig(
        database_url=database_url,
        database_backend=database_backend,
        log_level=log_level,
        timezone=timezone,
        data_provider=data_provider,
        external_api_enabled=external_api_enabled,
        root_dir=root,
        data_dir=data_dir,
        log_dir=log_dir,
        public_web_enabled=public_web_enabled,
        web_access_token=web_access_token,
        auto_seed_sample=_truthy(get("AUTO_SEED_SAMPLE", "true")),
        market_data_timeout_seconds=market_data_timeout_seconds,
        market_data_cache_ttl_hours=market_data_cache_ttl_hours,
        provider_retry_attempts=provider_retry_attempts,
        provider_retry_backoff_seconds=provider_retry_backoff_seconds,
        provider_circuit_failure_threshold=provider_circuit_failure_threshold,
        provider_circuit_reset_seconds=provider_circuit_reset_seconds,
        provider_alpaca_daily_budget=provider_alpaca_daily_budget,
        provider_finnhub_daily_budget=provider_finnhub_daily_budget,
        provider_yahoo_daily_budget=provider_yahoo_daily_budget,
        provider_sec_daily_budget=provider_sec_daily_budget,
        provider_openai_daily_budget=provider_openai_daily_budget,
        provider_template_daily_budget=provider_template_daily_budget,
        stooq_api_key=stooq_api_key,
        intraday_data_provider=intraday_data_provider,
        alpaca_api_key=alpaca_api_key,
        alpaca_api_secret=alpaca_api_secret,
        alpaca_data_feed=alpaca_data_feed,
        intraday_cache_ttl_seconds=intraday_cache_ttl_seconds,
        research_data_provider=research_data_provider,
        finnhub_api_key=finnhub_api_key,
        research_data_cache_ttl_hours=research_data_cache_ttl_hours,
        sec_company_facts_enabled=sec_company_facts_enabled,
        sec_user_agent=sec_user_agent,
        ai_summary_provider=ai_summary_provider,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        ai_summary_cache_ttl_hours=ai_summary_cache_ttl_hours,
        user_auth_enabled=user_auth_enabled,
        user_registration_enabled=user_registration_enabled,
        rate_limit_per_minute=rate_limit_per_minute,
        auth_rate_limit_per_minute=auth_rate_limit_per_minute,
        login_rate_limit_per_minute=login_rate_limit_per_minute,
        user_rate_limit_per_minute=user_rate_limit_per_minute,
        worker_rate_limit_per_minute=worker_rate_limit_per_minute,
        rate_limit_backend=rate_limit_backend,
        scan_queue_enabled=scan_queue_enabled,
        worker_token=worker_token,
        worker_cron_enabled=worker_cron_enabled,
        production_saas_mode=production_saas_mode,
        trusted_proxy_headers=trusted_proxy_headers,
        allow_query_token_auth=allow_query_token_auth,
        max_json_body_bytes=max_json_body_bytes,
        global_operator_emails=global_operator_emails,
        scan_mode=scan_mode,
        market_universe_provider=market_universe_provider,
        market_universe_max_symbols=market_universe_max_symbols,
        market_prefilter_limit=market_prefilter_limit,
        market_prefilter_provider=market_prefilter_provider,
        yahoo_prefilter_max_symbols=yahoo_prefilter_max_symbols,
        prefilter_time_budget_seconds=prefilter_time_budget_seconds,
        provider_fetch_workers=provider_fetch_workers,
        market_snapshot_batch_size=market_snapshot_batch_size,
        market_scan_requires_live_data=market_scan_requires_live_data,
    )


def doctor_report(config: AppConfig) -> dict[str, Any]:
    warnings: list[str] = []
    if not (config.root_dir / ".env").exists():
        warnings.append(".env is missing; safe defaults are active. Copy .env.example to .env for explicit config.")
    if config.data_provider == "sample":
        warnings.append("Sample data provider is active. No live market data is fetched.")
    if not config.external_api_enabled:
        warnings.append("External APIs are disabled, which is the safe private-beta default.")
    return {
        "database_backend": config.database_backend,
        "database_path": config.database_path if config.database_backend == "sqlite" else "<postgresql>",
        "log_dir": str(config.log_dir),
        "timezone": config.timezone,
        "data_provider": config.data_provider,
        "external_api_enabled": config.external_api_enabled,
        "public_web_enabled": config.public_web_enabled,
        "user_auth_enabled": config.user_auth_enabled,
        "user_registration_enabled": config.user_registration_enabled,
        "rate_limit_per_minute": config.rate_limit_per_minute,
        "auth_rate_limit_per_minute": config.auth_rate_limit_per_minute,
        "login_rate_limit_per_minute": config.login_rate_limit_per_minute,
        "user_rate_limit_per_minute": config.user_rate_limit_per_minute,
        "worker_rate_limit_per_minute": config.worker_rate_limit_per_minute,
        "rate_limit_backend": config.rate_limit_backend,
        "scan_queue_enabled": config.scan_queue_enabled,
        "worker_configured": len(config.worker_token) >= 16,
        "worker_cron_enabled": config.worker_cron_enabled,
        "production_saas_mode": config.production_saas_mode,
        "trusted_proxy_headers": config.trusted_proxy_headers,
        "allow_query_token_auth": config.allow_query_token_auth,
        "max_json_body_bytes": config.max_json_body_bytes,
        "global_operator_configured": bool(config.global_operator_emails),
        "market_data_cache_ttl_hours": config.market_data_cache_ttl_hours,
        "provider_retry_attempts": config.provider_retry_attempts,
        "provider_retry_backoff_seconds": config.provider_retry_backoff_seconds,
        "provider_circuit_failure_threshold": config.provider_circuit_failure_threshold,
        "provider_circuit_reset_seconds": config.provider_circuit_reset_seconds,
        "provider_daily_budgets": {
            "alpaca": config.provider_alpaca_daily_budget,
            "finnhub": config.provider_finnhub_daily_budget,
            "yahoo": config.provider_yahoo_daily_budget,
            "sec": config.provider_sec_daily_budget,
            "openai": config.provider_openai_daily_budget,
            "template": config.provider_template_daily_budget,
        },
        "intraday_data_provider": config.intraday_data_provider,
        "intraday_cache_ttl_seconds": config.intraday_cache_ttl_seconds,
        "research_data_provider": config.research_data_provider,
        "research_data_cache_ttl_hours": config.research_data_cache_ttl_hours,
        "sec_company_facts_enabled": config.sec_company_facts_enabled,
        "ai_summary_provider": config.ai_summary_provider,
        "ai_summary_cache_ttl_hours": config.ai_summary_cache_ttl_hours,
        "scan_mode": config.scan_mode,
        "market_universe_provider": config.market_universe_provider,
        "market_universe_max_symbols": config.market_universe_max_symbols,
        "market_prefilter_limit": config.market_prefilter_limit,
        "market_prefilter_provider": config.market_prefilter_provider,
        "prefilter_time_budget_seconds": config.prefilter_time_budget_seconds,
        "provider_fetch_workers": config.provider_fetch_workers,
        "market_snapshot_batch_size": config.market_snapshot_batch_size,
        "market_scan_requires_live_data": config.market_scan_requires_live_data,
        "warnings": warnings,
    }


def _parse_positive_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ValidationError(f"{name} must be greater than 0.")
    return value


def _parse_non_negative_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be a number.") from exc
    if value < 0:
        raise ValidationError(f"{name} must be 0 or greater.")
    return value


def _parse_positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValidationError(f"{name} must be greater than 0.")
    return value


def _database_backend(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return "sqlite"
    if database_url.startswith(("postgresql://", "postgres://")):
        return "postgresql"
    raise ValidationError("DATABASE_URL must start with sqlite:///, postgresql://, or postgres://.")


def _validate_production_saas_mode(
    *,
    database_backend: str,
    user_auth_enabled: bool,
    rate_limit_backend: str,
    scan_queue_enabled: bool,
    worker_token: str,
    worker_cron_enabled: bool,
) -> None:
    missing: list[str] = []
    if database_backend != "postgresql":
        missing.append("VCB_ALT_DATABASE_URL=postgresql://...")
    if not user_auth_enabled:
        missing.append("VCB_ALT_USER_AUTH_ENABLED=true")
    if rate_limit_backend != "database":
        missing.append("VCB_ALT_RATE_LIMIT_BACKEND=database")
    if not scan_queue_enabled:
        missing.append("VCB_ALT_SCAN_QUEUE_ENABLED=true")
    if len(worker_token) < 16:
        missing.append("VCB_ALT_WORKER_TOKEN=<long-random-token>")
    if not worker_cron_enabled:
        missing.append("VCB_ALT_WORKER_CRON_ENABLED=true")
    if missing:
        raise ValidationError(
            "Production SaaS mode requires durable auth, tenant storage, rate limiting, and scan queue settings: "
            + ", ".join(missing)
        )

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vcb_alt.providers as providers
from vcb_alt.config import AppConfig
from vcb_alt.db import add_watchlist, connect, init_db
from vcb_alt.errors import NotFoundError
from vcb_alt.web import handle_api


def main() -> int:
    report = run_provider_resilience_test()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


def run_provider_resilience_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = AppConfig(
            database_url="sqlite:///./data/provider-resilience.db",
            log_level="INFO",
            timezone="Asia/Seoul",
            data_provider="yahoo",
            external_api_enabled=True,
            root_dir=root,
            data_dir=root / "data",
            log_dir=root / "logs",
            market_data_timeout_seconds=1.0,
            market_data_cache_ttl_hours=1.0,
        )
        original_fetch = providers._fetch_yahoo_chart_json
        state = {"calls": 0}

        def budgeted_outage_fetch(
            ticker: str,
            timeout_seconds: float,
            range_value: str = "1y",
            config: AppConfig | None = None,
        ) -> str:
            state["calls"] += 1
            raise NotFoundError(f"Simulated provider outage or budget exhaustion for {ticker}.")

        try:
            providers._load_yahoo_bars_cached.cache_clear()
            providers._fetch_yahoo_chart_json = budgeted_outage_fetch
            with connect(config) as conn:
                init_db(conn)
                add_watchlist(conn, ["PLTR", "MSTR", "VST"])
            scan = handle_api(config, "GET", "/api/scan", "", None)
            select = handle_api(config, "GET", "/api/select", "", None)
        finally:
            providers._fetch_yahoo_chart_json = original_fetch
            providers._load_yahoo_bars_cached.cache_clear()

    failures = scan.data.get("failures", []) if scan.data else []
    return {
        "passed": bool(scan.ok and select.ok and len(failures) >= 3 and state["calls"] >= 3),
        "scan_ok": scan.ok,
        "select_ok": select.ok,
        "provider_calls_before_budget_stop": state["calls"],
        "failure_count": len(failures),
        "sample_failure": failures[0] if failures else None,
        "note": (
            "This is a deterministic outage/budget-exhaustion simulation. It proves the scan/select API "
            "returns structured provider failures instead of crashing. Production provider quota enforcement "
            "still needs vendor-specific limits and alerting."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())

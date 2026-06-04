from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a redacted hosted operations health report.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--access-token-env", default="VCB_ALT_WEB_ACCESS_TOKEN")
    parser.add_argument("--alert-webhook-env", default="VCB_ALT_ALERT_WEBHOOK_URL")
    parser.add_argument("--send-alert", action="store_true")
    args = parser.parse_args()
    report = collect_ops_report(args.base_url.rstrip("/"), args.timeout, os.getenv(args.access_token_env, ""))
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.send_alert:
        webhook = os.getenv(args.alert_webhook_env, "")
        if not webhook:
            raise SystemExit("Alert webhook env is missing.")
        _send_webhook(webhook, report, args.timeout)
    return 0 if report["overall_status"] == "ok" else 1


def collect_ops_report(base_url: str, timeout: float, access_token: str = "") -> dict[str, Any]:
    public_query = f"?token={access_token}" if access_token else ""
    checks = {
        "health": _get_json(f"{base_url}/api/health", timeout),
        "release_status": _get_json(f"{base_url}/api/release-status{public_query}", timeout),
        "provider_status": _get_json(f"{base_url}/api/provider-status{public_query}", timeout),
        "saas_readiness": _get_json(f"{base_url}/api/saas-readiness{public_query}", timeout),
    }
    failures = {
        name: value.get("message") or value.get("error") for name, value in checks.items() if not value.get("ok")
    }
    release = checks["release_status"].get("data") or {}
    configured = release.get("configured_data") if isinstance(release.get("configured_data"), dict) else {}
    provider = checks["provider_status"].get("data") or {}
    return {
        "overall_status": "ok" if not failures else "degraded",
        "failures": failures,
        "production_saas_ready": bool(release.get("production_saas_ready")),
        "public_launch_ready": bool(release.get("public_launch_ready")),
        "release_channel": release.get("release_channel"),
        "database_backend": configured.get("database_backend") or release.get("database_backend"),
        "queue_enabled": configured.get("scan_queue_enabled") or release.get("scan_queue_enabled"),
        "worker_cron_enabled": configured.get("worker_cron_enabled") or release.get("worker_cron_enabled"),
        "user_auth_enabled": configured.get("user_auth_enabled") or release.get("user_auth_enabled"),
        "rate_limit_backend": configured.get("rate_limit_backend") or release.get("rate_limit_backend"),
        "market_provider": provider.get("provider"),
        "research_provider": provider.get("research_data_provider"),
        "intraday_provider": provider.get("intraday_data_provider"),
        "provider_warnings": provider.get("warnings", []),
        "used_access_token": bool(access_token),
        "checked_endpoints": list(checks),
    }


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "vcb-alt-ops-health-report/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "message": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _send_webhook(webhook_url: str, report: dict[str, Any], timeout: float) -> None:
    payload = json.dumps({"text": f"VCB-Alt ops status: {report['overall_status']}", "report": report}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "vcb-alt-ops-health-report/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


if __name__ == "__main__":
    raise SystemExit(main())

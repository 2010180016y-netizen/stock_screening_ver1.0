from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


DEFAULT_TICKERS = ["PLTR", "MSTR", "VST"]
DEFAULT_BASE_URL = "https://stockscreeningver10.vercel.app"
USER_AGENT = "vcb-alt-host-queue-load-test/2.0"


@dataclass(frozen=True)
class UserFlowResult:
    ok: bool
    email: str
    token: str
    job_kind: str
    job_id: str
    enqueue_status: str
    elapsed_ms: float
    error: str = ""


@dataclass(frozen=True)
class RequestRecord:
    label: str
    status_code: int
    elapsed_ms: float
    ok: bool


class RequestError(RuntimeError):
    def __init__(self, label: str, status_code: int, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.label = label
        self.status_code = status_code
        self.payload = payload or {}


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: list[RequestRecord] = []
        self.errors: list[str] = []

    def record(self, label: str, status_code: int, elapsed_ms: float, ok: bool) -> None:
        with self._lock:
            self.records.append(RequestRecord(label, status_code, elapsed_ms, ok))

    def error(self, message: str) -> None:
        with self._lock:
            self.errors.append(message[:300])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self.records)
            errors = list(self.errors)
        latencies = sorted(record.elapsed_ms for record in records)
        by_label: dict[str, list[float]] = {}
        http_status_counts: dict[str, int] = {}
        for record in records:
            by_label.setdefault(record.label, []).append(record.elapsed_ms)
            class_key = f"{record.status_code // 100}xx" if record.status_code else "0xx"
            http_status_counts[class_key] = http_status_counts.get(class_key, 0) + 1
            code_key = str(record.status_code)
            http_status_counts[code_key] = http_status_counts.get(code_key, 0) + 1
        return {
            "request_count": len(records),
            "http_status_counts": http_status_counts,
            "latency_ms": _latency_summary(latencies),
            "latency_by_stage_ms": {
                label: _latency_summary(sorted(values))
                for label, values in sorted(by_label.items())
            },
            "sample_errors": errors[:10],
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run hosted 1000-user SaaS scan-heavy load test against auth, queue, worker, polling, and snapshot APIs."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--poll-seconds", type=float, default=300.0)
    parser.add_argument("--trigger-worker", action="store_true")
    parser.add_argument("--worker-token-env", default="VCB_ALT_WORKER_TOKEN")
    parser.add_argument("--access-token-env", default="VCB_ALT_WEB_ACCESS_TOKEN")
    parser.add_argument("--worker-limit", type=int, default=100)
    parser.add_argument("--simulate-distributed-ips", action="store_true")
    parser.add_argument("--confirm-production-load", action="store_true")
    parser.add_argument("--confirm-provider-budget", action="store_true")
    parser.add_argument("--max-provider-calls", type=int, default=250)
    parser.add_argument("--expected-provider-calls", type=int, default=230)
    parser.add_argument("--min-provider-budget-remaining", type=int, default=250)
    parser.add_argument("--snapshot-read-sample", type=int, default=1000)
    parser.add_argument("--skip-auth-preflight", action="store_true")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    try:
        report = run_hosted_load_test(
            base_url=args.base_url,
            users=args.users,
            concurrency=args.concurrency,
            tickers=[ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()],
            timeout=args.timeout,
            poll_seconds=args.poll_seconds,
            trigger_worker=args.trigger_worker,
            worker_token=os.getenv(args.worker_token_env, ""),
            access_token=os.getenv(args.access_token_env, ""),
            worker_limit=args.worker_limit,
            simulate_distributed_ips=args.simulate_distributed_ips,
            confirm_production_load=args.confirm_production_load,
            confirm_provider_budget=args.confirm_provider_budget,
            max_provider_calls=args.max_provider_calls,
            expected_provider_calls=args.expected_provider_calls,
            min_provider_budget_remaining=args.min_provider_budget_remaining,
            snapshot_read_sample=args.snapshot_read_sample,
            run_auth_preflight=not args.skip_auth_preflight,
            cleanup_accounts=not args.skip_cleanup,
        )
    except ValueError as exc:
        report = _blocked_preflight_report(
            base_url=args.base_url,
            users=args.users,
            concurrency=args.concurrency,
            trigger_worker=args.trigger_worker,
            worker_token_present=bool(os.getenv(args.worker_token_env, "")),
            worker_token_env=args.worker_token_env,
            reason=str(exc),
        )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0 if report["judgment"]["load_test_passed"] else 1


def run_hosted_load_test(
    *,
    base_url: str,
    users: int,
    concurrency: int,
    tickers: list[str],
    timeout: float,
    poll_seconds: float,
    trigger_worker: bool,
    worker_token: str,
    access_token: str,
    worker_limit: int,
    simulate_distributed_ips: bool,
    confirm_production_load: bool,
    confirm_provider_budget: bool,
    max_provider_calls: int,
    expected_provider_calls: int,
    min_provider_budget_remaining: int,
    snapshot_read_sample: int,
    run_auth_preflight: bool,
    cleanup_accounts: bool,
) -> dict[str, Any]:
    _validate_args(
        users=users,
        concurrency=concurrency,
        trigger_worker=trigger_worker,
        worker_token=worker_token,
        worker_limit=worker_limit,
        confirm_production_load=confirm_production_load,
        confirm_provider_budget=confirm_provider_budget,
        max_provider_calls=max_provider_calls,
        expected_provider_calls=expected_provider_calls,
    )
    base = base_url.rstrip("/")
    metrics = Metrics()
    run_id = str(int(time.time()))
    public_query = _access_query(access_token)
    started = time.perf_counter()

    health = _safe_get(metrics, "health", f"{base}/api/health", timeout)
    provider_before = _safe_get(metrics, "provider_health_before", f"{base}/api/provider-health{public_query}", timeout)
    release_status = _safe_get(metrics, "release_status", f"{base}/api/release-status{public_query}", timeout)
    preflight_checks = _hosted_preflight_checks(
        metrics,
        base,
        run_id,
        timeout,
        run_auth_preflight=run_auth_preflight,
    )
    if trigger_worker and len(worker_token) < 16:
        return _final_report(
            base=base,
            users=users,
            concurrency=concurrency,
            trigger_worker=trigger_worker,
            started=started,
            metrics=metrics,
            health=health,
            release_status=release_status,
            provider_before=provider_before,
            provider_after=None,
            preflight_checks=preflight_checks,
            budget_guard={
                "enabled": trigger_worker,
                "blocked": True,
                "reason": "Worker trigger requires a token in --worker-token-env.",
                "provider_calls_allowed": False,
            },
            flow_results=[],
            worker_runs=[],
            unique_jobs={},
            polled_jobs={},
            snapshot_reads=[],
            queue_status=None,
            provider_alerts=None,
            cleanup=[],
            reason="worker token preflight blocked",
        )
    budget_guard = _provider_budget_guard(
        provider_before,
        trigger_worker=trigger_worker,
        confirm_provider_budget=confirm_provider_budget,
        expected_provider_calls=expected_provider_calls,
        max_provider_calls=max_provider_calls,
        min_provider_budget_remaining=min_provider_budget_remaining,
    )
    if budget_guard["blocked"]:
        return _final_report(
            base=base,
            users=users,
            concurrency=concurrency,
            trigger_worker=trigger_worker,
            started=started,
            metrics=metrics,
            health=health,
            release_status=release_status,
            provider_before=provider_before,
            provider_after=None,
            preflight_checks=preflight_checks,
            budget_guard=budget_guard,
            flow_results=[],
            worker_runs=[],
            unique_jobs={},
            polled_jobs={},
            snapshot_reads=[],
            queue_status=None,
            provider_alerts=None,
            cleanup=[],
            reason="provider budget guard blocked worker execution",
        )

    flow_results = _run_registration_enqueue_flows(
        metrics,
        base,
        run_id,
        users,
        concurrency,
        tickers,
        timeout,
        simulate_distributed_ips,
    )
    admin_token = next((result.token for result in flow_results if result.token), "")
    admin_headers = _auth_headers(admin_token)
    unique_jobs = _unique_jobs(flow_results)

    worker_runs: list[dict[str, Any]] = []
    if trigger_worker and unique_jobs:
        worker_runs = _trigger_workers_until_terminal(
            metrics,
            base,
            worker_token,
            worker_limit,
            timeout,
            poll_seconds,
            unique_jobs,
            admin_headers,
        )

    polled_jobs = _poll_unique_jobs(metrics, base, unique_jobs, admin_headers, timeout, poll_seconds)
    snapshot_reads = _run_snapshot_reads(
        metrics,
        base,
        flow_results,
        timeout,
        max_reads=min(max(0, snapshot_read_sample), len(flow_results)),
    )
    queue_status = _safe_get(metrics, "queue_status", f"{base}/api/admin/queue-status", timeout, admin_headers)
    provider_alerts = _safe_get(metrics, "provider_alerts", f"{base}/api/admin/provider-alerts?limit=20", timeout, admin_headers)
    provider_after = _safe_get(metrics, "provider_health_after", f"{base}/api/provider-health{public_query}", timeout)
    cleanup = _cleanup_test_accounts(metrics, base, flow_results, timeout) if cleanup_accounts else []

    return _final_report(
        base=base,
        users=users,
        concurrency=concurrency,
        trigger_worker=trigger_worker,
        started=started,
        metrics=metrics,
        health=health,
        release_status=release_status,
        provider_before=provider_before,
        provider_after=provider_after,
        preflight_checks=preflight_checks,
        budget_guard=budget_guard,
        flow_results=flow_results,
        worker_runs=worker_runs,
        unique_jobs=unique_jobs,
        polled_jobs=polled_jobs,
        snapshot_reads=snapshot_reads,
        queue_status=queue_status,
        provider_alerts=provider_alerts,
        cleanup=cleanup,
        reason="completed",
    )


def _validate_args(
    *,
    users: int,
    concurrency: int,
    trigger_worker: bool,
    worker_token: str,
    worker_limit: int,
    confirm_production_load: bool,
    confirm_provider_budget: bool,
    max_provider_calls: int,
    expected_provider_calls: int,
) -> None:
    if users < 1 or users > 1000:
        raise ValueError("users must be between 1 and 1000.")
    if concurrency < 1 or concurrency > 100:
        raise ValueError("concurrency must be between 1 and 100.")
    if users > 50 and not confirm_production_load:
        raise ValueError("Use --confirm-production-load for more than 50 hosted users.")
    if worker_limit < 1 or worker_limit > 100:
        raise ValueError("worker-limit must be between 1 and 100.")
    if trigger_worker and not confirm_provider_budget:
        raise ValueError("Use --confirm-provider-budget to acknowledge provider budget guard settings.")
    if expected_provider_calls > max_provider_calls:
        raise ValueError("expected-provider-calls cannot exceed max-provider-calls.")


def _blocked_preflight_report(
    *,
    base_url: str,
    users: int,
    concurrency: int,
    trigger_worker: bool,
    worker_token_present: bool,
    worker_token_env: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "base_url": base_url.rstrip("/"),
        "run_type": "hosted_scan_heavy_1000_user",
        "reason": "preflight_blocked",
        "users": users,
        "concurrency": concurrency,
        "trigger_worker": trigger_worker,
        "preflight": {
            "blocked": True,
            "reason": reason,
            "worker_token_env": worker_token_env,
            "worker_token_present": worker_token_present,
        },
        "success_rate": 0,
        "registration_login_enqueue": {"ok": 0, "failed": users, "status_counts": {}, "unique_jobs": {}},
        "worker": {
            "triggered": trigger_worker,
            "runs": [],
            "processed_count": 0,
            "failed_count": 0,
            "completion_count": 0,
            "terminal_count": 0,
        },
        "jobs": {},
        "snapshot_reads": {"attempted": 0, "ok": 0, "failed": 0, "sample": []},
        "queue_depth": None,
        "db_error_count": 0,
        "provider": {
            "budget_guard": {
                "blocked": trigger_worker,
                "reason": reason,
                "provider_calls_allowed": False,
            },
            "health_before": None,
            "health_after": None,
            "call_count_delta": {},
            "failure_count": 0,
            "failures": [],
        },
        "metrics": {
            "request_count": 0,
            "http_status_counts": {},
            "latency_ms": _latency_summary([]),
            "latency_by_stage_ms": {},
            "sample_errors": [reason],
        },
        "judgment": {
            "load_test_passed": False,
            "operable_for_1000_user_saas": False,
            "decision": "NOT_READY_FOR_1000_USER_SAAS",
            "reason": "Hosted 1000-user scan-heavy test was blocked before execution by missing prerequisites.",
        },
    }


def _run_registration_enqueue_flows(
    metrics: Metrics,
    base: str,
    run_id: str,
    users: int,
    concurrency: int,
    tickers: list[str],
    timeout: float,
    simulate_distributed_ips: bool,
) -> list[UserFlowResult]:
    results: list[UserFlowResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                _run_user_enqueue_flow,
                metrics,
                base,
                run_id,
                index,
                tickers,
                timeout,
                _simulated_ip(index) if simulate_distributed_ips else "",
            )
            for index in range(users)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _cleanup_test_accounts(
    metrics: Metrics,
    base: str,
    flow_results: list[UserFlowResult],
    timeout: float,
) -> list[dict[str, Any]]:
    cleanup: list[dict[str, Any]] = []
    for result in flow_results:
        if not result.token:
            continue
        try:
            response = _json_request(
                metrics,
                "account_delete",
                f"{base}/api/user/account?confirm=DELETE_MY_ACCOUNT",
                "DELETE",
                None,
                timeout=timeout,
                headers=_auth_headers(result.token),
            )
            cleanup.append({"email": result.email, "ok": bool(response.get("ok")), "status": response.get("_status_code")})
        except RequestError as exc:
            cleanup.append({"email": result.email, "ok": False, "status": exc.status_code, "error": str(exc)[:160]})
    return cleanup


def _hosted_preflight_checks(
    metrics: Metrics,
    base: str,
    run_id: str,
    timeout: float,
    *,
    run_auth_preflight: bool,
) -> dict[str, Any]:
    return {
        "worker_protection": _probe_worker_protection(metrics, base, timeout),
        "auth_register_login_delete": (
            _probe_auth_register_login_delete(metrics, base, run_id, timeout)
            if run_auth_preflight
            else {"attempted": False, "ok": None, "reason": "skipped by --skip-auth-preflight"}
        ),
    }


def _probe_worker_protection(metrics: Metrics, base: str, timeout: float) -> dict[str, Any]:
    try:
        response = _json_request(
            metrics,
            "worker_protection_probe",
            f"{base}/api/admin/run-worker?limit=1",
            "POST",
            {},
            timeout,
            {},
        )
        return {
            "attempted": True,
            "ok": False,
            "protected": False,
            "status_code": response.get("_status_code"),
            "reason": "Worker endpoint accepted an unauthenticated trigger.",
        }
    except RequestError as exc:
        protected = exc.status_code in {401, 403}
        return {
            "attempted": True,
            "ok": protected,
            "protected": protected,
            "status_code": exc.status_code,
            "reason": "Worker endpoint rejected unauthenticated trigger." if protected else str(exc)[:200],
        }
    except Exception as exc:
        metrics.error(f"worker_protection_probe: {exc}")
        return {"attempted": True, "ok": False, "protected": None, "status_code": 0, "reason": str(exc)[:200]}


def _probe_auth_register_login_delete(metrics: Metrics, base: str, run_id: str, timeout: float) -> dict[str, Any]:
    email = f"host-preflight-{run_id}@example.invalid"
    password = f"Preflight-{run_id}-password"
    token = ""
    cleanup: dict[str, Any] = {"attempted": False, "ok": None}
    try:
        registered = _json_request(
            metrics,
            "preflight_register",
            f"{base}/api/auth/register",
            "POST",
            {"email": email, "password": password, "tenant_name": f"host-preflight-{run_id}"},
            timeout,
            {},
        )
        token = str((registered.get("data") or {}).get("session_token") or "")
        logged_in = _json_request(
            metrics,
            "preflight_login",
            f"{base}/api/auth/login",
            "POST",
            {"email": email, "password": password},
            timeout,
            {},
        )
        token = str((logged_in.get("data") or {}).get("session_token") or token)
        if token:
            deleted = _json_request(
                metrics,
                "preflight_account_delete",
                f"{base}/api/user/account?confirm=DELETE_MY_ACCOUNT",
                "DELETE",
                None,
                timeout,
                _auth_headers(token),
            )
            cleanup = {"attempted": True, "ok": bool(deleted.get("ok")), "status_code": deleted.get("_status_code")}
        return {
            "attempted": True,
            "ok": True,
            "email_domain": "example.invalid",
            "register_status": registered.get("_status_code"),
            "login_status": logged_in.get("_status_code"),
            "cleanup": cleanup,
        }
    except Exception as exc:
        metrics.error(f"preflight_auth: {exc}")
        cleanup_error = ""
        if token:
            try:
                deleted = _json_request(
                    metrics,
                    "preflight_account_delete",
                    f"{base}/api/user/account?confirm=DELETE_MY_ACCOUNT",
                    "DELETE",
                    None,
                    timeout,
                    _auth_headers(token),
                )
                cleanup = {"attempted": True, "ok": bool(deleted.get("ok")), "status_code": deleted.get("_status_code")}
            except Exception as cleanup_exc:
                cleanup_error = str(cleanup_exc)[:200]
        return {
            "attempted": True,
            "ok": False,
            "email_domain": "example.invalid",
            "reason": str(exc)[:200],
            "cleanup": {**cleanup, "error": cleanup_error} if cleanup_error else cleanup,
        }


def _run_user_enqueue_flow(
    metrics: Metrics,
    base: str,
    run_id: str,
    index: int,
    tickers: list[str],
    timeout: float,
    simulated_ip: str,
) -> UserFlowResult:
    started = time.perf_counter()
    email = f"host-load-{run_id}-{index}@example.invalid"
    password = f"LoadTest-{run_id}-{index}-password"
    client_headers = _client_headers(simulated_ip)
    token = ""
    stage = "register"
    try:
        registered = _json_request(
            metrics,
            "register",
            f"{base}/api/auth/register",
            "POST",
            {"email": email, "password": password, "tenant_name": f"host-load-{run_id}-{index}"},
            timeout,
            client_headers,
        )
        stage = "login"
        logged_in = _json_request(
            metrics,
            "login",
            f"{base}/api/auth/login",
            "POST",
            {"email": email, "password": password},
            timeout,
            client_headers,
        )
        token = str(logged_in["data"]["session_token"])
        headers = {**_auth_headers(token), **client_headers}
        if tickers:
            stage = "optional_watchlist"
            _json_request(
                metrics,
                "optional_watchlist",
                f"{base}/api/user/watchlist",
                "POST",
                {"tickers": " ".join(tickers), "metadata": {"load_test_optional": True}},
                timeout,
                headers,
            )
        stage = "scan_enqueue"
        queued = _json_request(metrics, "scan_enqueue", f"{base}/api/jobs/scan", "POST", {}, timeout, headers)
        job = _extract_job_ref(queued.get("data"))
        return UserFlowResult(
            ok=True,
            email=email,
            token=token,
            job_kind=job["kind"],
            job_id=job["id"],
            enqueue_status=job["status"],
            elapsed_ms=_elapsed_ms(started),
        )
    except Exception as exc:
        message = f"{stage}: {exc}"
        metrics.error(message)
        return UserFlowResult(False, email, token, "", "", "error", _elapsed_ms(started), error=message[:300])


def _trigger_workers_until_terminal(
    metrics: Metrics,
    base: str,
    worker_token: str,
    worker_limit: int,
    timeout: float,
    poll_seconds: float,
    unique_jobs: dict[str, dict[str, str]],
    admin_headers: dict[str, str],
) -> list[dict[str, Any]]:
    worker_runs: list[dict[str, Any]] = []
    deadline = time.perf_counter() + max(1.0, poll_seconds)
    while time.perf_counter() < deadline:
        query = urllib.parse.urlencode({"limit": str(worker_limit)})
        try:
            payload = _json_request(
                metrics,
                "worker_trigger",
                f"{base}/api/admin/run-worker?{query}",
                "POST",
                {},
                timeout,
                {"Authorization": f"Bearer {worker_token}"},
            )
            worker_runs.append(dict(payload.get("data") or {}))
        except Exception as exc:
            metrics.error(f"worker_trigger: {exc}")
            break
        polled = _poll_unique_jobs(metrics, base, unique_jobs, admin_headers, timeout, poll_seconds=1.0, once=True)
        if _all_jobs_terminal(polled):
            break
        time.sleep(1.0)
    return worker_runs


def _poll_unique_jobs(
    metrics: Metrics,
    base: str,
    unique_jobs: dict[str, dict[str, str]],
    headers: dict[str, str],
    timeout: float,
    poll_seconds: float,
    *,
    once: bool = False,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    deadline = time.perf_counter() + max(1.0, poll_seconds)
    while True:
        for key, job in unique_jobs.items():
            if results.get(key, {}).get("status") in {"completed", "failed", "dead_letter"}:
                continue
            endpoint = (
                f"{base}/api/jobs/market-scan/{urllib.parse.quote(job['id'])}"
                if job["kind"] == "market"
                else f"{base}/api/jobs/{urllib.parse.quote(job['id'])}"
            )
            try:
                payload = _json_request(metrics, f"poll_{job['kind']}_job", endpoint, "GET", None, timeout, headers)
                data = dict(payload.get("data") or {})
                results[key] = data
            except Exception as exc:
                metrics.error(f"poll_{job['kind']}_job: {exc}")
                results[key] = {"status": "poll_error", "message": str(exc)}
        if once or _all_jobs_terminal(results) or time.perf_counter() >= deadline:
            return results
        time.sleep(1.0)


def _run_snapshot_reads(
    metrics: Metrics,
    base: str,
    flows: list[UserFlowResult],
    timeout: float,
    *,
    max_reads: int,
) -> list[dict[str, Any]]:
    readable = [flow for flow in flows if flow.token and flow.ok][:max_reads]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(50, max(1, len(readable)))) as pool:
        futures = [
            pool.submit(_snapshot_read, metrics, base, flow, timeout)
            for flow in readable
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _snapshot_read(metrics: Metrics, base: str, flow: UserFlowResult, timeout: float) -> dict[str, Any]:
    try:
        payload = _json_request(
            metrics,
            "snapshot_read",
            f"{base}/api/user/scan",
            "POST",
            {},
            timeout,
            _auth_headers(flow.token),
        )
        data = dict(payload.get("data") or {})
        return {
            "ok": True,
            "status_code": int(payload.get("_status_code", 200)),
            "state": data.get("state") or data.get("snapshot", {}).get("status") or data.get("scan_mode"),
            "count": data.get("count", 0),
            "snapshot": data.get("snapshot", {}),
        }
    except Exception as exc:
        metrics.error(f"snapshot_read: {exc}")
        return {"ok": False, "error": str(exc)}


def _safe_get(
    metrics: Metrics,
    label: str,
    url: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        return _json_request(metrics, label, url, "GET", None, timeout, headers)
    except Exception as exc:
        metrics.error(f"{label}: {exc}")
        return None


def _json_request(
    metrics: Metrics,
    label: str,
    url: str,
    method: str,
    body: dict[str, Any] | None,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
    )
    status_code = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        raw = exc.read().decode("utf-8") or "{}"
    elapsed = _elapsed_ms(started)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        metrics.record(label, status_code, elapsed, False)
        raise RequestError(label, status_code, f"malformed JSON: {exc}") from exc
    ok = bool(data.get("ok"))
    data["_status_code"] = status_code
    metrics.record(label, status_code, elapsed, ok)
    if not ok:
        error = data.get("error") if isinstance(data.get("error"), dict) else {}
        message = str(error.get("message") or data.get("message") or f"HTTP {status_code}")
        raise RequestError(label, status_code, message, data)
    return data


def _provider_budget_guard(
    provider_before: dict[str, Any] | None,
    *,
    trigger_worker: bool,
    confirm_provider_budget: bool,
    expected_provider_calls: int,
    max_provider_calls: int,
    min_provider_budget_remaining: int,
) -> dict[str, Any]:
    guard = {
        "enabled": trigger_worker,
        "confirmed": confirm_provider_budget,
        "expected_provider_calls": expected_provider_calls,
        "max_provider_calls": max_provider_calls,
        "min_provider_budget_remaining": min_provider_budget_remaining,
        "blocked": False,
        "reason": "",
        "provider_budget_remaining": {},
    }
    if not trigger_worker:
        return guard
    if expected_provider_calls > max_provider_calls:
        guard["blocked"] = True
        guard["reason"] = "expected provider calls exceed max-provider-calls"
        return guard
    if not provider_before or not provider_before.get("ok"):
        guard["blocked"] = True
        guard["reason"] = "provider health was unavailable; refusing provider-heavy worker trigger"
        return guard
    providers = provider_before.get("data", {}).get("providers", {})
    for name, state in providers.items():
        if not isinstance(state, dict) or not state.get("configured"):
            continue
        remaining = int(state.get("budget", {}).get("remaining", 0) or 0)
        guard["provider_budget_remaining"][name] = remaining
        if remaining < min_provider_budget_remaining:
            guard["blocked"] = True
            guard["reason"] = f"{name} remaining provider budget below guard"
            return guard
    return guard


def _final_report(
    *,
    base: str,
    users: int,
    concurrency: int,
    trigger_worker: bool,
    started: float,
    metrics: Metrics,
    health: dict[str, Any] | None,
    release_status: dict[str, Any] | None,
    provider_before: dict[str, Any] | None,
    provider_after: dict[str, Any] | None,
    preflight_checks: dict[str, Any],
    budget_guard: dict[str, Any],
    flow_results: list[UserFlowResult],
    worker_runs: list[dict[str, Any]],
    unique_jobs: dict[str, dict[str, str]],
    polled_jobs: dict[str, dict[str, Any]],
    snapshot_reads: list[dict[str, Any]],
    queue_status: dict[str, Any] | None,
    provider_alerts: dict[str, Any] | None,
    cleanup: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    elapsed = time.perf_counter() - started
    ok_flows = [flow for flow in flow_results if flow.ok]
    failed_flows = [flow for flow in flow_results if not flow.ok]
    snapshot_ok = [item for item in snapshot_reads if item.get("ok")]
    terminal_jobs = [job for job in polled_jobs.values() if job.get("status") in {"completed", "failed", "dead_letter"}]
    completed_jobs = [job for job in polled_jobs.values() if job.get("status") == "completed"]
    provider_failures = _provider_failures(polled_jobs, provider_alerts)
    cleanup_ok = [item for item in cleanup if item.get("ok")]
    worker_processed = sum(int(run.get("processed", 0) or 0) for run in worker_runs)
    worker_failed = sum(int(run.get("failed", 0) or 0) for run in worker_runs)
    status_counts: dict[str, int] = {}
    for flow in flow_results:
        status_key = flow.enqueue_status or flow.error or "unknown"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
    load_test_passed = (
        not budget_guard.get("blocked")
        and len(ok_flows) == users
        and (not trigger_worker or bool(completed_jobs))
        and not provider_failures
        and worker_failed == 0
        and (not snapshot_reads or len(snapshot_ok) == len(snapshot_reads))
        and (not cleanup or len(cleanup_ok) == len(cleanup))
    )
    return {
        "base_url": base,
        "run_type": "hosted_scan_heavy_1000_user",
        "reason": reason,
        "users": users,
        "concurrency": concurrency,
        "trigger_worker": trigger_worker,
        "elapsed_seconds": round(elapsed, 3),
        "flows_per_second": round(users / elapsed, 2) if elapsed and users else 0,
        "success_rate": round((len(ok_flows) / users) * 100, 2) if users else 0,
        "registration_login_enqueue": {
            "ok": len(ok_flows),
            "failed": len(failed_flows),
            "status_counts": status_counts,
            "unique_jobs": unique_jobs,
            "sample_errors": [flow.error for flow in failed_flows[:10]],
        },
        "worker": {
            "triggered": trigger_worker,
            "runs": worker_runs,
            "processed_count": worker_processed,
            "failed_count": worker_failed,
            "completion_count": len(completed_jobs),
            "terminal_count": len(terminal_jobs),
        },
        "jobs": polled_jobs,
        "snapshot_reads": {
            "attempted": len(snapshot_reads),
            "ok": len(snapshot_ok),
            "failed": len(snapshot_reads) - len(snapshot_ok),
            "sample": snapshot_reads[:5],
        },
        "cleanup": {
            "attempted": len(cleanup),
            "ok": len(cleanup_ok),
            "failed": len(cleanup) - len(cleanup_ok),
            "sample": cleanup[:5],
        },
        "queue_depth": _queue_depth(queue_status),
        "db_error_count": _db_error_count(metrics, polled_jobs, provider_alerts),
        "preflight": preflight_checks,
        "provider": {
            "budget_guard": budget_guard,
            "health_before": _compact_provider_health(provider_before),
            "health_after": _compact_provider_health(provider_after),
            "call_count_delta": _provider_call_count_delta(provider_before, provider_after),
            "failure_count": len(provider_failures),
            "failures": provider_failures[:10],
            "failure_handling": _provider_failure_handling_summary(
                provider_before=provider_before,
                provider_alerts=provider_alerts,
                polled_jobs=polled_jobs,
                provider_failures=provider_failures,
                budget_guard=budget_guard,
            ),
        },
        "release_status": release_status.get("data") if release_status else None,
        "health": health.get("data") if health else None,
        "metrics": metrics.snapshot(),
        "judgment": {
            "load_test_passed": load_test_passed,
            "operable_for_1000_user_saas": False,
            "decision": "NOT_READY_FOR_1000_USER_SAAS",
            "reason": (
                "Hosted 1000-user scan-heavy test passed technically, but public SaaS remains blocked by release/legal/provider gates."
                if load_test_passed
                else "Hosted 1000-user scan-heavy test did not prove safe operation; inspect provider, queue, worker, and DB metrics."
            ),
        },
    }


def _extract_job_ref(data: Any) -> dict[str, str]:
    payload = data if isinstance(data, dict) else {}
    if isinstance(payload.get("job"), dict):
        job = payload["job"]
        return {
            "kind": "market" if str(job.get("id", "")).startswith("market_") else "tenant",
            "id": str(job.get("id") or ""),
            "status": str(payload.get("status") or job.get("status") or payload.get("state") or ""),
        }
    if payload.get("id"):
        return {"kind": "tenant", "id": str(payload["id"]), "status": str(payload.get("status") or "")}
    if payload.get("state") == "fresh":
        return {"kind": "snapshot", "id": "", "status": "fresh"}
    return {"kind": "unknown", "id": "", "status": str(payload.get("status") or payload.get("state") or "unknown")}


def _unique_jobs(flows: list[UserFlowResult]) -> dict[str, dict[str, str]]:
    jobs: dict[str, dict[str, str]] = {}
    for flow in flows:
        if not flow.job_id:
            continue
        key = f"{flow.job_kind}:{flow.job_id}"
        jobs[key] = {"kind": flow.job_kind, "id": flow.job_id}
    return jobs


def _all_jobs_terminal(jobs: dict[str, dict[str, Any]]) -> bool:
    return bool(jobs) and all(job.get("status") in {"completed", "failed", "dead_letter", "poll_error"} for job in jobs.values())


def _provider_failures(polled_jobs: dict[str, dict[str, Any]], provider_alerts: dict[str, Any] | None) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for job in polled_jobs.values():
        if job.get("error_code") or job.get("status") in {"failed", "dead_letter"}:
            failures.append(
                {
                    "source": "job",
                    "status": job.get("status"),
                    "error_code": job.get("error_code"),
                    "message": job.get("message"),
                }
            )
    for item in (provider_alerts or {}).get("data", {}).get("items", []):
        if isinstance(item, dict):
            failures.append(
                {
                    "source": "provider_alert",
                    "provider": item.get("provider"),
                    "severity": item.get("severity"),
                    "code": item.get("code"),
                    "message": item.get("message"),
                    "recovery": item.get("recovery"),
                }
            )
    return failures


def _provider_failure_handling_summary(
    *,
    provider_before: dict[str, Any] | None,
    provider_alerts: dict[str, Any] | None,
    polled_jobs: dict[str, dict[str, Any]],
    provider_failures: list[dict[str, Any]],
    budget_guard: dict[str, Any],
) -> dict[str, Any]:
    health_checked = bool(provider_before)
    job_failure_path_checked = bool(polled_jobs)
    alert_path_checked = provider_alerts is not None
    return {
        "health_budget_checked": health_checked,
        "job_failure_path_checked": job_failure_path_checked,
        "admin_alert_path_checked": alert_path_checked,
        "failure_count": len(provider_failures),
        "budget_guard_blocked_provider_calls": bool(budget_guard.get("blocked")),
        "covered_in_this_run": health_checked and (job_failure_path_checked or alert_path_checked),
        "not_exercised_reason": (
            ""
            if health_checked and (job_failure_path_checked or alert_path_checked)
            else "Worker trigger/admin context was unavailable, so hosted job failure and provider-alert paths were not exercised."
        ),
    }


def _queue_depth(queue_status: dict[str, Any] | None) -> dict[str, Any]:
    data = (queue_status or {}).get("data") if isinstance(queue_status, dict) else {}
    if not isinstance(data, dict):
        return {"available": False}
    market = data.get("market_scan_snapshots", {}) if isinstance(data.get("market_scan_snapshots"), dict) else {}
    return {
        "available": True,
        "tenant_queued": data.get("queued"),
        "tenant_running": data.get("running"),
        "tenant_failed": data.get("failed"),
        "tenant_completed": data.get("completed"),
        "market_queued": market.get("queued"),
        "market_running": market.get("running"),
        "market_failed": market.get("failed"),
        "market_dead_letter": market.get("dead_letter"),
        "market_completed": market.get("completed"),
        "market_latest": market.get("latest"),
    }


def _db_error_count(metrics: Metrics, jobs: dict[str, dict[str, Any]], provider_alerts: dict[str, Any] | None) -> int:
    text = json.dumps({"metrics": metrics.snapshot(), "jobs": jobs, "alerts": provider_alerts}, ensure_ascii=False).lower()
    return sum(text.count(term) for term in ("database", "postgres", "psycopg", "sql", "deadlock"))


def _compact_provider_health(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload or not payload.get("ok"):
        return None
    providers = payload.get("data", {}).get("providers", {})
    compact: dict[str, Any] = {}
    for name, state in providers.items():
        if isinstance(state, dict):
            compact[name] = {
                "configured": state.get("configured"),
                "status": state.get("status"),
                "budget": state.get("budget"),
                "circuit": state.get("circuit"),
                "total_requests": state.get("total_requests"),
                "total_failures": state.get("total_failures"),
                "last_error_code": state.get("last_error_code"),
            }
    return compact


def _provider_call_count_delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, int | None]:
    before_health = _compact_provider_health(before) or {}
    after_health = _compact_provider_health(after) or {}
    names = sorted(set(before_health) | set(after_health))
    delta: dict[str, int | None] = {}
    for name in names:
        before_count = before_health.get(name, {}).get("total_requests")
        after_count = after_health.get(name, {}).get("total_requests")
        delta[name] = int(after_count) - int(before_count) if before_count is not None and after_count is not None else None
    return delta


def _access_query(access_token: str) -> str:
    return f"?{urllib.parse.urlencode({'token': access_token})}" if access_token else ""


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _client_headers(simulated_ip: str) -> dict[str, str]:
    return {"X-Forwarded-For": simulated_ip} if simulated_ip else {}


def _simulated_ip(index: int) -> str:
    third = index // 250
    fourth = (index % 250) + 1
    return f"198.18.{third}.{fourth}"


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(statistics.median(values), 2) if values else 0.0,
        "p95": round(_percentile(values, 95), 2) if values else 0.0,
        "p99": round(_percentile(values, 99), 2) if values else 0.0,
        "max": round(max(values), 2) if values else 0.0,
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[index]


if __name__ == "__main__":
    raise SystemExit(main())

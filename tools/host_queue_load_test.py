from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


DEFAULT_TICKERS = ["PLTR", "MSTR", "VST", "AAPL", "GME", "RGTI", "SMMT"]


@dataclass(frozen=True)
class FlowResult:
    ok: bool
    status: str
    elapsed_ms: float
    job_id: str = ""
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hosted SaaS queue load smoke against auth/watchlist/job APIs.")
    parser.add_argument("--base-url", required=True, help="Example: https://stockscreeningver10.vercel.app")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--trigger-worker", action="store_true")
    parser.add_argument("--worker-token-env", default="VCB_ALT_WORKER_TOKEN")
    parser.add_argument("--worker-limit", type=int, default=100)
    parser.add_argument("--simulate-distributed-ips", action="store_true")
    parser.add_argument("--confirm-production-load", action="store_true")
    args = parser.parse_args()
    report = run_queue_load_test(
        base_url=args.base_url,
        users=args.users,
        concurrency=args.concurrency,
        tickers=[ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()],
        timeout=args.timeout,
        poll_seconds=args.poll_seconds,
        trigger_worker=args.trigger_worker,
        worker_token=os.getenv(args.worker_token_env, ""),
        worker_limit=args.worker_limit,
        simulate_distributed_ips=args.simulate_distributed_ips,
        confirm_production_load=args.confirm_production_load,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.trigger_worker:
        return 0 if report["errors"] == 0 and report["completed_jobs"] == report["users"] else 1
    return 0 if report["errors"] == 0 and report["queued_jobs"] == report["users"] else 1


def run_queue_load_test(
    *,
    base_url: str,
    users: int,
    concurrency: int,
    tickers: list[str],
    timeout: float,
    poll_seconds: float,
    trigger_worker: bool,
    worker_token: str,
    worker_limit: int,
    simulate_distributed_ips: bool,
    confirm_production_load: bool,
) -> dict[str, Any]:
    if users < 1 or users > 1000:
        raise ValueError("users must be between 1 and 1000")
    if concurrency < 1 or concurrency > 100:
        raise ValueError("concurrency must be between 1 and 100")
    if users > 50 and not confirm_production_load:
        raise ValueError("Use --confirm-production-load for more than 50 hosted users.")
    if trigger_worker and len(worker_token) < 16:
        raise ValueError("Worker trigger requires a token in --worker-token-env.")
    if worker_limit < 1 or worker_limit > 100:
        raise ValueError("worker-limit must be between 1 and 100.")
    base = base_url.rstrip("/")
    run_id = str(int(time.time()))
    started = time.perf_counter()
    results: list[FlowResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                _run_user_flow,
                base,
                run_id,
                index,
                tickers,
                timeout,
                poll_seconds,
                trigger_worker,
                worker_token,
                worker_limit,
                _simulated_ip(index) if simulate_distributed_ips else "",
            )
            for index in range(users)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started
    latencies = sorted(result.elapsed_ms for result in results)
    statuses: dict[str, int] = {}
    for result in results:
        statuses[result.status] = statuses.get(result.status, 0) + 1
    errors = sum(1 for result in results if not result.ok)
    return {
        "base_url": base,
        "users": users,
        "concurrency": concurrency,
        "tickers_per_user": len(tickers),
        "trigger_worker": trigger_worker,
        "simulate_distributed_ips": simulate_distributed_ips,
        "worker_limit": worker_limit,
        "elapsed_seconds": round(elapsed, 3),
        "flows_per_second": round(users / elapsed, 2) if elapsed else users,
        "status_counts": statuses,
        "queued_jobs": sum(1 for result in results if result.job_id),
        "completed_jobs": statuses.get("completed", 0),
        "errors": errors,
        "latency_ms_median": round(statistics.median(latencies), 2) if latencies else 0,
        "latency_ms_p95": round(_percentile(latencies, 95), 2) if latencies else 0,
        "latency_ms_max": round(max(latencies), 2) if latencies else 0,
        "sample_errors": [result.error for result in results if result.error][:5],
    }


def _run_user_flow(
    base_url: str,
    run_id: str,
    index: int,
    tickers: list[str],
    timeout: float,
    poll_seconds: float,
    trigger_worker: bool,
    worker_token: str,
    worker_limit: int,
    simulated_ip: str,
) -> FlowResult:
    started = time.perf_counter()
    email = f"load-{run_id}-{index}@example.invalid"
    password = f"LoadTest-{run_id}-{index}-password"
    client_headers = _client_headers(simulated_ip)
    stage = "register"
    try:
        registered = _json_request(
            f"{base_url}/api/auth/register",
            "POST",
            {"email": email, "password": password, "tenant_name": f"load-{run_id}-{index}"},
            timeout,
            client_headers,
        )
        token = registered["data"]["session_token"]
        headers = {"Authorization": f"Bearer {token}", **client_headers}
        stage = "watchlist"
        _json_request(f"{base_url}/api/user/watchlist", "POST", {"tickers": " ".join(tickers)}, timeout, headers)
        stage = "queue"
        queued = _json_request(f"{base_url}/api/jobs/scan", "POST", {}, timeout, headers)
        job_id = str(queued["data"]["id"])
        if trigger_worker:
            stage = "worker"
            query = urllib.parse.urlencode({"limit": str(worker_limit)})
            _json_request(
                f"{base_url}/api/admin/run-worker?{query}",
                "POST",
                {},
                timeout,
                {"Authorization": f"Bearer {worker_token}", **client_headers},
            )
        stage = "poll"
        status = _poll_job(base_url, job_id, headers, timeout, poll_seconds)
        ok = status == "completed" or (not trigger_worker and status in {"queued", "running"})
        return FlowResult(ok, status, _elapsed_ms(started), job_id=job_id)
    except Exception as exc:
        return FlowResult(False, "error", _elapsed_ms(started), error=f"{stage}: {exc}"[:240])


def _poll_job(base_url: str, job_id: str, headers: dict[str, str], timeout: float, poll_seconds: float) -> str:
    deadline = time.perf_counter() + max(1.0, poll_seconds)
    status = "queued"
    while time.perf_counter() < deadline:
        payload = _json_request(f"{base_url}/api/jobs/{urllib.parse.quote(job_id)}", "GET", None, timeout, headers)
        status = str(payload["data"]["status"])
        if status in {"completed", "failed"}:
            return status
        time.sleep(1.0)
    return status


def _json_request(
    url: str,
    method: str,
    body: dict[str, Any] | None,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "vcb-alt-host-queue-load-test/1.0",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        data = json.loads(exc.read().decode("utf-8") or "{}")
    if not data.get("ok"):
        error = data.get("error") or {}
        raise RuntimeError(str(error.get("message") or data.get("message") or "request failed"))
    return data


def _client_headers(simulated_ip: str) -> dict[str, str]:
    if not simulated_ip:
        return {}
    return {"X-Forwarded-For": simulated_ip}


def _simulated_ip(index: int) -> str:
    # 198.18.0.0/15 is reserved for benchmark and network test traffic.
    third = index // 250
    fourth = (index % 250) + 1
    return f"198.18.{third}.{fourth}"


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[index]


if __name__ == "__main__":
    raise SystemExit(main())

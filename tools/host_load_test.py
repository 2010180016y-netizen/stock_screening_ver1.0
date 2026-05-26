from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative hosted HTTP load smoke test.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    report = run_host_load_test(args.url, args.requests, args.concurrency, args.timeout)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["errors"] == 0 and report["status_2xx"] == args.requests else 1


def run_host_load_test(url: str, requests: int, concurrency: int, timeout: float) -> dict[str, object]:
    if requests < 1 or requests > 10_000:
        raise ValueError("requests must be between 1 and 10000")
    if concurrency < 1 or concurrency > 250:
        raise ValueError("concurrency must be between 1 and 250")
    started = time.perf_counter()
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    errors = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_request_once, url, timeout) for _ in range(requests)]
        for future in as_completed(futures):
            status, elapsed_ms = future.result()
            latencies.append(elapsed_ms)
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            if status < 200 or status >= 400:
                errors += 1
    elapsed = time.perf_counter() - started
    sorted_latencies = sorted(latencies)
    return {
        "url": url,
        "requests": requests,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(requests / elapsed, 2) if elapsed else requests,
        "status_counts": statuses,
        "status_2xx": sum(count for status, count in statuses.items() if 200 <= int(status) < 300),
        "errors": errors,
        "latency_ms_min": round(min(sorted_latencies), 2),
        "latency_ms_median": round(statistics.median(sorted_latencies), 2),
        "latency_ms_p95": round(_percentile(sorted_latencies, 95), 2),
        "latency_ms_max": round(max(sorted_latencies), 2),
    }


def _request_once(url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "vcb-alt-host-load-test/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
    except Exception:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[index]


if __name__ == "__main__":
    raise SystemExit(main())

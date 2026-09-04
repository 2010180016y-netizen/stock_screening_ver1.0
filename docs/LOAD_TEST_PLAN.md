# Load Test Plan

Last updated: 2026-05-22

## 1. Why This Exists

The current CLI can be tested locally, but it cannot prove readiness for 1000 users. This plan defines the future SaaS load tests that must pass before public or 1000-user beta exposure.

2026-05-19 update: a local SaaS-boundary load simulator now exists at `tools/load_test.py`. It exercises the per-user/tenant schema and scoring path without external market-data calls. This is a meaningful engineering smoke test, but it is not a substitute for a deployed PostgreSQL/API staging load test.

2026-05-21 update: hosted load-test tooling now exists at `tools/host_load_test.py`, and the app has database-backed rate limiting plus queue-backed tenant scans.

2026-05-22 update: hosted `/api/health` load smoke test passed for `1000` requests at concurrency `25` with `0` errors.

Second 2026-05-22 update: after Neon PostgreSQL cutover, hosted `/api/health` load smoke test passed again for `1000` requests at concurrency `25` with `0` errors and p95 latency `1917.36ms`. This proves the deployed health/control-plane path stayed available under light HTTP concurrency; it does not prove scan-heavy queue readiness.

## 2. Workloads

### Read Heavy

- 100 concurrent users fetching dashboard/latest evaluations.
- 5-minute steady-state run.
- p95 < 500 ms.
- Error rate < 1%.

### On-Demand Evaluation

- 50 concurrent users requesting cached ticker evaluations.
- p95 < 2 s.
- No duplicate job explosion for same `(user, ticker)`.

### Daily Scan

- 1000 users.
- 30 tickers each.
- 30,000 ticker evaluations.
- Completion < 30 minutes with cached market data.

Hosted queue command:

```powershell
python tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 50 --concurrency 10 --trigger-worker --worker-token-env VCB_ALT_WORKER_TOKEN
```

For more than 50 hosted users, add `--confirm-production-load` after confirming provider budget and operator approval.

### Provider Outage

- Simulate provider 503 or timeout.
- Workers must retry with backoff.
- Dead-letter after max attempts.
- UI/API must show pending/failure state.

Deterministic local simulation:

```powershell
python tools\provider_resilience_test.py
```

### Tenant Isolation Under Load

- Generate two tenants with overlapping tickers.
- Confirm responses never include the other tenant's rows.

## 3. Metrics To Capture

- API p50/p95/p99 latency
- API status counts
- DB query duration
- DB connection count
- Queue depth
- Oldest job age
- Worker throughput
- Provider request count
- Cache hit rate
- Error budget burn

## 4. Exit Criteria

- All workloads pass twice in staging.
- No tenant-isolation failure.
- No secret appears in logs.
- Provider budget enforcement works.
- Operators can find failed jobs within 2 minutes.

## 5. Local Simulation Result

Command:

```powershell
python tools\load_test.py --users 1000 --tickers 30
```

Result:

- Users: `1000`
- Tickers per user: `30`
- Evaluations: `30000`
- Elapsed: `23.786` seconds
- Throughput: `1261.24` evaluations/second
- p95 user flow: `13.892` ms
- Errors: `0`
- Tenant isolation: `passed`

Remaining required staging tests:

- Same scan-heavy workload against managed PostgreSQL through the deployed queue path.
- Real deployed HTTP API concurrency test for auth, watchlist, queue creation, job polling, and worker processing.
- Hosted health smoke command:

```powershell
python tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 1000 --concurrency 25 --timeout 15
```

Hosted health smoke result:

- Requests: `1000`
- Status `200`: `1000`
- Errors: `0`
- Elapsed: `50.838` seconds
- Throughput: `19.67` requests/second
- Median latency: `1200.6` ms
- P95 latency: `1917.36` ms
- Max latency: `4569.66` ms

- Database-backed rate-limit test against the production PostgreSQL deployment.
- Provider outage and budget-enforcement test.
- Backup/restore drill during loaded state.

## 6. New Tooling Added 2026-05-22

- `tools/host_queue_load_test.py`: hosted auth/watchlist/queue/job-polling load smoke.
- `tools/provider_resilience_test.py`: deterministic provider outage/budget-exhaustion simulation.
- `tools/ops_health_report.py`: redacted health/release/provider/readiness operations report with optional webhook alert.
- `tools/queue_load_test.py`: local queue-backed 1000-user scan simulation.

Local queue-backed result:

```powershell
python tools\queue_load_test.py --users 1000 --tickers 30 --worker-limit 100
```

- Users: `1000`
- Queued jobs: `1000`
- Completed jobs: `1000`
- Failed jobs: `0`
- Tenant evaluations: `30000`
- Elapsed: `66.014s`
- Throughput: `454.45 evaluations/s`

## 7. Worker-Triggered Hosted Completion Result 2026-05-24

Command:

```powershell
python tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 10 --concurrency 2 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 90 --trigger-worker
```

Result:

- Users: `10`
- Queued jobs: `10`
- Completed jobs: `10`
- Errors: `0`
- Trigger worker: `true`
- P95 latency: `5019.1ms`

Higher-load single-runner attempt:

```powershell
python tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 50 --concurrency 2 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 120 --trigger-worker
```

Result:

- Users: `50`
- Queued jobs: `24`
- Completed jobs: `24`
- Errors: `26`
- Failure mode: `Rate limit exceeded. Try again later.`

Interpretation:

- The deployed queue plus protected worker endpoint can complete hosted jobs.
- The current single-machine test runner cannot be used as a faithful 1000-user public load test because all traffic comes from one source and correctly trips the production durable rate limiter.
- The remaining 1000-user public-launch test should run from a distributed hosted load-testing service or a staging profile with explicit test-only rate-limit keys.

## 8. Full Hosted 1000-User Completion Result 2026-05-24

Before this run, endpoint-specific durable rate-limit buckets were added:

- unauthenticated auth/signup bucket
- authenticated per-user/per-tenant bucket
- protected worker bucket
- default IP bucket

Command:

```powershell
python tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load
```

Result:

- Deployment: `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`
- Users: `1000`
- Queued jobs: `1000`
- Completed jobs: `1000`
- Errors: `0`
- Trigger worker: `true`
- Worker limit: `100`
- Concurrency: `20`
- Tickers per user: `3`
- Elapsed: `243.152s`
- Median latency: `4685.17ms`
- P95 latency: `6049.49ms`
- Max latency: `17311.08ms`

Post-run health:

- `300/300` health requests returned HTTP `200`
- Errors: `0`
- P95 latency: `1572.27ms`
- 15-minute production `500` log query returned no new error entries

# Monitoring And Incident Runbook

Last updated: 2026-06-03 KST

## Current State

- `/api/health` reports process health without database DDL side effects.
- `/api/release-status` reports owner/operator-trial status, public-launch gate state, auth, queue, worker, and provider configuration.
- `/api/provider-status` reports provider capabilities and warnings without exposing secrets.
- `/api/provider-health` reports provider budget, circuit-breaker, timeout/retry, and fail-closed policy state without exposing secrets.
- `/api/admin/provider-alerts` reports durable provider alert events for owner/admin users.
- `/api/admin/queue-status` reports tenant and market-snapshot queue counts for owner/admin users.
- `tools/ops_health_report.py` collects a redacted health summary and can send a webhook.

Current launch posture remains `operator_trial`; do not use monitoring green checks as public-launch approval.

## Required Dashboards

API:

- request rate by route
- 2xx/4xx/5xx counts
- p50/p95/p99 latency
- auth/signup/login error rate
- rate-limit rejects by bucket

Queue and worker:

- market snapshot queued/running/completed/failed/dead-letter count
- tenant scan queued/running/completed/failed count
- oldest queued job age
- worker trigger count and worker processed/failed count
- retry and dead-letter rate

Provider:

- Alpaca/Finnhub/Yahoo/SEC/OpenAI/template request count
- provider failure count by code
- quota budget remaining
- circuit breaker open/closed state
- fallback mode used

Database:

- Neon availability
- connection count and pool saturation
- query latency
- lock waits
- storage growth
- backup/restore status
- migration drift check status

Security and abuse:

- login failure spike
- registration spike
- session failures
- worker endpoint auth failures
- scan enqueue volume per tenant/IP
- export/delete/admin endpoint access

## Alert Rules

| Alert | Threshold | Severity | First response |
|---|---:|---|---|
| API 5xx rate | > 2% for 5 minutes | P1 | Check Vercel logs and recent deploy |
| Health check failure | 2 consecutive failures | P1 | Verify deployment and Neon status |
| Queue oldest job age | > 10 minutes | P1 | Run queue backlog runbook |
| Market snapshot dead-letter | >= 1 live-data job | P1 | Run provider and worker runbooks |
| Worker failures | > 5 in 10 minutes | P1 | Pause worker retries if failures grow |
| Provider failure rate | > 20% for 10 minutes | P1 | Run provider outage runbook |
| Provider budget remaining | < configured guard | P1 | Stop provider-heavy worker runs |
| Neon connection saturation | > 80% for 5 minutes | P1 | Run DB error runbook |
| Auth abuse | > 20 failures per IP/hour | P1 | Run auth abuse runbook |
| Rate-limit rejects | > 10% for 5 minutes | P2 | Run rate-limit saturation runbook |
| Backup missing | no successful backup in 24 hours | P1 | Run Neon backup drill |

## Health Command

```powershell
python tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app --timeout 20
```

Optional webhook:

```powershell
$env:VCB_ALT_ALERT_WEBHOOK_URL="https://hooks.example.invalid/..."
python tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app --send-alert
```

## Incident: Provider Outage Or Budget Exhaustion

Detection:

- `/api/provider-health` shows `degraded`, `budget_exhausted`, or `circuit_open`.
- `/api/admin/provider-alerts` has `PROVIDER_AUTH_FAILED`, `PROVIDER_RATE_LIMITED`, `PROVIDER_BUDGET_EXHAUSTED`, `PROVIDER_TIMEOUT`, `PROVIDER_NETWORK_ERROR`, or `PROVIDER_MALFORMED_JSON`.
- Market snapshot jobs fail or move to `dead_letter`.

Immediate action:

1. Stop repeated hosted scan-heavy runs.
2. Confirm `MARKET_SCAN_REQUIRES_LIVE_DATA=true` keeps final candidate output fail-closed.
3. Do not enable sample/demo fallback in production.
4. Check provider status pages and account quota.
5. For Alpaca auth failures, run `/api/provider-diagnostics/alpaca` and rotate the Key ID/Secret pair if needed.
6. For quota/budget failures, reduce worker frequency/batch size or wait for the provider window to reset.

Recovery:

1. Confirm provider health returns to `ready`.
2. Trigger one protected worker run with a small limit.
3. Confirm one market snapshot job completes.
4. Confirm `/api/user/scan` reads a fresh snapshot.
5. Reopen larger hosted tests only after provider budget remains above guard thresholds.

Public status:

- Keep product status as owner/operator trial.
- Do not advertise live market-wide discovery while final candidate output is fail-closed.

## Incident: Worker Failure

Detection:

- `/api/admin/queue-status` shows queued/running jobs not progressing.
- Worker run returns failures.
- Market snapshot status remains `running` beyond stale threshold.

Immediate action:

1. Inspect `/api/admin/queue-status`.
2. Inspect `/api/jobs/market-scan/{id}` for attempts, error code, retry time, and message.
3. Check Vercel function logs for worker route errors.
4. Verify worker token configuration; do not print the token.
5. Pause manual worker triggering if errors are provider-originated and growing.

Recovery:

1. Fix provider/config/DB issue first.
2. Re-run protected worker with a small `limit`.
3. Confirm stale-running recovery requeues jobs or sends exhausted jobs to `dead_letter`.
4. Clear only confirmed duplicate or test jobs; do not delete production user jobs without incident approval.

## Incident: Queue Backlog

Detection:

- Oldest queued job age exceeds 10 minutes.
- `market_scan_snapshots` has active queued/running jobs that do not complete.
- Users receive repeated `202 queued/pending` without a fresh snapshot.

Immediate action:

1. Check if provider circuits or budgets are blocking worker completion.
2. Check Neon connection saturation and slow queries.
3. Increase worker run limit only if provider budgets allow it.
4. If abuse is suspected, tighten registration/scan rate limits before increasing worker capacity.

Recovery:

1. Complete or dead-letter the oldest job.
2. Confirm a fresh market snapshot is available.
3. Confirm concurrent users share the same snapshot/job id instead of causing duplicate provider calls.

## Incident: Database Error Or Neon Degradation

Detection:

- API 5xx errors with DB messages.
- Neon dashboard reports connection saturation, branch issue, storage exhaustion, or query latency regression.
- `tools/ops_health_report.py` fails release/provider/config checks.

Immediate action:

1. Stop deployments and migrations.
2. Stop provider-heavy worker triggers if DB writes are failing.
3. Check Neon metrics: availability, connections, CPU, storage, lock waits, slow queries.
4. Run read-only schema/table checks if the DB is reachable.
5. If data loss or corruption is suspected, start `NEON_BACKUP_RESTORE_DRILL.md`.

Recovery:

1. Restore to a new Neon branch if corruption is confirmed.
2. Repoint staging first and run migration drift plus sample tenant integrity checks.
3. Repoint production only after staging verification.
4. Keep the old branch for forensic review.

## Incident: Auth Abuse

Detection:

- Login failures exceed threshold.
- Registration spikes unexpectedly.
- Session failures or admin endpoint access attempts spike.
- Worker endpoint receives unauthorized traffic.

Immediate action:

1. Disable open registration if enabled.
2. Tighten auth and user API rate limits.
3. Rotate shared public web token if it appears in logs/screenshots.
4. Block abusive IPs at the edge/WAF layer when available.
5. Review tenant audit events and admin endpoint access.

Recovery:

1. Confirm login failure rate returns to baseline.
2. Confirm no unauthorized tenant/admin access occurred.
3. If a secret leaked, rotate it and record incident evidence.

## Incident: Rate-Limit Saturation

Detection:

- 429 rate-limit rejects exceed 10% for 5 minutes.
- Hosted load tests or single-runner traffic trigger durable bucket limits.
- Legitimate users cannot enqueue scans or read snapshots.

Immediate action:

1. Identify the saturated bucket: auth, user API, worker, or default public API.
2. Separate abuse from expected hosted load test behavior.
3. Do not globally raise rate limits without checking provider budget and DB capacity.
4. For hosted tests, use explicit test windows and distributed sources; keep provider budget guards enabled.

Recovery:

1. Adjust only the affected bucket.
2. Re-run a small smoke test.
3. Record p50/p95/p99 latency, 4xx/5xx counts, and provider call deltas.

## Remaining Work

- Connect Vercel and Neon metrics to a durable alerting system owned by the operator.
- Add request IDs to API responses and logs.
- Add hosted alert delivery credentials.
- Run the first Neon staging restore drill.
- Run a hosted scan-heavy worker completion load test with the operator-held worker token and provider budget guards.

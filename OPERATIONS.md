# Operations Runbook

## Daily Flow

```powershell
python -m vcb_alt scan
python -m vcb_alt select
python -m vcb_alt admin failures
```

Review candidates manually. The system does not place trades.

## Web Dashboard

Run:

```powershell
python -m vcb_alt web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The dashboard auto-loads watchlist/research context, scan results when providers are healthy, final candidate selection, failure count, and SaaS readiness status.

For a token-protected owner/operator trial, set `VCB_ALT_PUBLIC_WEB_ENABLED=true` and a long `VCB_ALT_WEB_ACCESS_TOKEN`, then run behind HTTPS:

```powershell
python -m vcb_alt web --host 0.0.0.0 --port 8765
```

Do not treat the token gate as public SaaS authentication. Current production status is owner/operator trial only: `public_launch_ready=false` and `NOT_READY_FOR_1000_USER_SAAS`.

## Performance Check

```powershell
python -m vcb_alt benchmark --repeat 1000
```

This measures local scoring throughput without external market data calls.

## Add Or Remove Tickers

```powershell
python -m vcb_alt watchlist add PLTR MSTR RGTI
python -m vcb_alt watchlist remove AAPL
python -m vcb_alt watchlist list
```

## Run With Current Manual Data

1. Update `data/snapshots.csv`.
2. Confirm `.env` has `VCB_ALT_DATA_PROVIDER=manual`.
3. Run:

```powershell
python -m vcb_alt scan
python -m vcb_alt select
```

If a watchlist ticker has no row in `data/snapshots.csv`, the scan records a failed job instead of inventing a score.

## Run With Automatic Market Data

Set:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
```

Then run the normal daily flow. The provider caches responses under `data/market_cache/` for `VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS`.

If provider fetches fail, check:

- Network/DNS access from the host
- Unsupported ticker symbols
- Cache directory write permissions
- `admin failures` for the provider error

## Alpaca Live Scan Diagnostics

Before representing market-universe results as live provider-backed scans, check:

```text
/api/provider-diagnostics/alpaca
```

Required state:

- `ready=true`
- Paper or Live Trading API accepted
- Market Data snapshot endpoint accepted
- `/api/user/scan` returns `scan_mode=market_universe` without sample fallback

If diagnostics returns `key_context_mismatch_or_invalid`, regenerate the Alpaca Key ID and Secret Key as one matching pair, update Vercel Production variables, redeploy, and rerun diagnostics.

## Provider Health, Budgets, And Alerts

Provider-heavy work must run through the worker-owned scan path. The app now applies the same resilience policy to Alpaca, Finnhub, Yahoo, SEC, OpenAI, and the local template summary provider:

- Timeout: `VCB_ALT_MARKET_DATA_TIMEOUT_SECONDS`.
- Retry attempts: `VCB_ALT_PROVIDER_RETRY_ATTEMPTS`.
- Retry backoff: `VCB_ALT_PROVIDER_RETRY_BACKOFF_SECONDS`.
- Circuit breaker threshold/reset: `VCB_ALT_PROVIDER_CIRCUIT_FAILURE_THRESHOLD`, `VCB_ALT_PROVIDER_CIRCUIT_RESET_SECONDS`.
- Daily quota budgets: `VCB_ALT_PROVIDER_ALPACA_DAILY_BUDGET`, `VCB_ALT_PROVIDER_FINNHUB_DAILY_BUDGET`, `VCB_ALT_PROVIDER_YAHOO_DAILY_BUDGET`, `VCB_ALT_PROVIDER_SEC_DAILY_BUDGET`, `VCB_ALT_PROVIDER_OPENAI_DAILY_BUDGET`.

Operator endpoints:

- `GET /api/provider-health`: current provider policy, process-local request/failure/budget/circuit state, and fallback policy. This endpoint never returns API keys or secrets.
- `GET /api/admin/provider-alerts`: durable provider alert events for owner/admin users.
- `GET /api/provider-diagnostics/alpaca`: credential/feed diagnostics for Alpaca, still secret-safe.

Fail-closed rule:

- In production with `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true`, final market-universe candidate output must not use sample/demo fallback.
- If Alpaca snapshots/assets, Yahoo chart data, Finnhub quota, SEC metadata, or OpenAI explanation summaries fail, the worker must either use a permitted non-candidate fallback or block final candidate output with a provider error.
- OpenAI is explanation-only. If OpenAI times out or fails, the deterministic template summary is used; it does not select stocks.

Provider recovery:

1. Open `/api/provider-health` and confirm which provider is `degraded`, `budget_exhausted`, or `circuit_open`.
2. Open `/api/admin/provider-alerts` and inspect `code`, `message`, `recovery`, and `metadata`.
3. For Alpaca `PROVIDER_AUTH_FAILED`, regenerate Key ID and Secret as one matching pair, verify paper/live account context and feed (`iex` vs `sip`), update production variables, redeploy, and rerun `/api/provider-diagnostics/alpaca`.
4. For `PROVIDER_RATE_LIMITED` or `PROVIDER_BUDGET_EXHAUSTED`, reduce worker frequency/batch size or upgrade the provider plan; do not rerun hosted scans until the provider window resets.
5. For `PROVIDER_TIMEOUT` or `PROVIDER_NETWORK_ERROR`, check provider status, Vercel/network egress, and DNS before increasing timeout.
6. For `PROVIDER_MALFORMED_JSON`, keep live candidate output blocked until the provider returns valid JSON or a fresh cache/snapshot is available.

Logging rule:

- Provider alert metadata is redacted before storage.
- Do not paste API keys into `.env` screenshots, ticket text, ticker notes, or command arguments.
- If a secret is suspected in logs, rotate it and treat the old value as compromised.

## Worker-Owned Market Scan Snapshots

Production SaaS market-universe scans are worker-owned. User requests must not directly call Alpaca, Finnhub, Yahoo, SEC, or explanation-summary providers.

Runtime behavior:

- `POST /api/user/scan`
  - returns `200` with the latest fresh durable market snapshot when one exists.
  - returns `202` with `state=queued` or `state=pending` and a market job id when no fresh snapshot exists.
- `POST /api/jobs/scan`
  - follows the same market snapshot enqueue/read behavior in `market_universe` mode.
- `GET /api/jobs/market-scan/{id}`
  - returns the global market snapshot job status, attempts, error code, retry time, report, provider metadata, and failures.
- `POST /api/admin/run-worker?worker_token=<token>`
  - processes queued market snapshot jobs before tenant watchlist jobs.

Durable storage:

- `market_scan_snapshots.report_json`: full API scan report.
- `market_scan_snapshots.selected_json`: selected candidates.
- `market_scan_snapshots.provider_metadata_json`: universe, prefilter, count, elapsed time, and provider scan metadata.
- `market_scan_snapshots.failures_json`: provider and evaluation failures.
- `market_scan_snapshots.expires_at`: freshness boundary for user-facing reads.

Concurrency policy:

- Only one queued/running market snapshot refresh is allowed per `scan_key`.
- Concurrent users share the same fresh snapshot or the same queued/running job id.
- Provider-heavy work happens in the worker, not in `/api/user/scan`.

Failure policy:

- Running snapshot jobs that exceed the stale threshold are requeued while attempts remain.
- Provider failures are retried with backoff up to the max-attempt limit.
- Exhausted jobs move to `dead_letter`.
- Operators should inspect `/api/admin/queue-status`, `/api/jobs/market-scan/{id}`, and `/api/provider-diagnostics/alpaca` before inviting users.

## Investigate A Failure

```powershell
python -m vcb_alt admin failures --json
python -m vcb_alt admin logs --json
```

Check:

- Error code
- Failed command
- Timestamp
- Whether the database was initialized
- Whether ticker input was valid

## Export Data

```powershell
python -m vcb_alt admin export --out exports\vcb_export.json
```

## Delete Local Data

```powershell
python -m vcb_alt admin delete-data --confirm DELETE_LOCAL_DATA
```

This clears watchlist, evaluations, operation logs, and failed jobs from the SQLite DB. It does not remove `.env`, source files, or exported files.

## Security Rules

- Keep `.env` local.
- Enable external APIs only when the intended provider is configured and cache settings are understood.
- Rotate `VCB_ALT_WEB_ACCESS_TOKEN` if it is shared too widely or appears in logs, screenshots, or messages.
- Do not paste API keys into ticker notes or command arguments.
- Treat results as decision support only.

## Incident Checklist

1. Stop repeated runs if failures are growing.
2. Export data if possible.
3. Review `admin failures`.
4. Review `logs/app.log`.
5. Restore DB from backup if corruption is suspected.
6. Re-run `doctor` and `self-test`.

## Production Incident Entry Points

Current production is owner/operator trial only. Do not convert an incident workaround into unrestricted external-release approval.

Provider outage or provider budget exhaustion:

1. Open `/api/provider-health`.
2. Open `/api/admin/provider-alerts` as an owner/admin.
3. Keep `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true`; do not enable sample/demo candidate fallback.
4. Stop hosted scan-heavy tests until provider health and budget return to safe levels.
5. Follow `MONITORING_ALERTING_PLAN.md#incident-provider-outage-or-budget-exhaustion`.

Worker failure:

1. Open `/api/admin/queue-status`.
2. Open `/api/jobs/market-scan/{id}` for the oldest queued/running market snapshot.
3. Confirm the worker token is configured without printing or sharing it.
4. Trigger only a small protected worker run after provider and DB health are clear.
5. Follow `MONITORING_ALERTING_PLAN.md#incident-worker-failure`.

Queue backlog:

1. Check oldest queued job age and active `market_scan_snapshots`.
2. Confirm concurrent users are sharing a snapshot/job id and not creating duplicate provider-heavy jobs.
3. Increase worker limit only if provider budgets allow it.
4. Follow `MONITORING_ALERTING_PLAN.md#incident-queue-backlog`.

Database or Neon error:

1. Stop deployments, migrations, and provider-heavy worker runs.
2. Check Neon connection count, query latency, lock waits, storage, and branch status.
3. Run `tools/ops_health_report.py` for redacted API evidence.
4. If corruption or data loss is suspected, start `NEON_BACKUP_RESTORE_DRILL.md` on a staging restore branch before touching production.

Auth abuse:

1. Disable registration if it is open.
2. Tighten auth/user rate-limit buckets.
3. Rotate shared tokens if exposed.
4. Review tenant audit events and admin endpoint access.
5. Follow `MONITORING_ALERTING_PLAN.md#incident-auth-abuse`.

Rate-limit saturation:

1. Identify the saturated bucket: auth, user API, worker, or default public API.
2. Keep provider budget guards enabled.
3. Treat single-runner hosted load-test 429s as expected protection unless real users are affected.
4. Follow `MONITORING_ALERTING_PLAN.md#incident-rate-limit-saturation`.

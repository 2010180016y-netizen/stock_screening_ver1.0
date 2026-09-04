# Go-Live Runbook

Follow this on the day you re-issue the Alpaca credentials. It takes the deployment from
"running but showing no candidates" to "live market scan verified", and it is the only
document you need open — the steps that used to be spread across
`PROVIDER_KEYS_SETUP.md`, `OPERATOR_TRIAL_GUIDE.md` and `RELEASE_DECISION.md` are
collected here.

Written for a non-specialist. Every step says what to type, what you should see, and what
it means if you see something else. Nothing here requires editing code.

**Never paste a key, token or secret into this file, a commit message, a chat, or an
issue.** Values belong only in the Vercel environment-variable screen.

---

## Vocabulary

Four terms appear throughout.

| Term | What it means here |
| --- | --- |
| **Provider** | An outside company whose market data we read: Alpaca (live quotes), Finnhub (fundamentals and news), Yahoo (daily prices), SEC (filings). |
| **Worker** | A background job that runs the market scan and saves the result. Users read the saved result; they never trigger a scan directly. |
| **Snapshot** | One saved scan result, with a timestamp. "Fresh" means recent enough to serve. |
| **Fail-closed** | When live data is unavailable the app shows nothing rather than guessing or falling back to sample data. Seeing no candidates is the system working correctly, not a crash. |

---

## Step 0 — Rotate the leaked access token (do this first)

The operator-trial access token was committed in plain text in this repository's history.
Until it is replaced, anyone who has seen the repository can open the deployment.

1. Generate a new random value of 32 characters or more. Any password generator works.
2. In the Vercel project, open **Settings → Environment Variables**, Production scope.
3. Set `VCB_ALT_WEB_ACCESS_TOKEN` to the new value.

The application refuses to start if the old leaked value is configured again, so a
mistake here fails loudly rather than silently.

**Expected result:** the variable shows a recent "Updated" timestamp. The new value is
visible only to you.

---

## Step 1 — Set the environment variables

All of these live in Vercel, Production scope. Names only below; you supply the values.

### Live market data (the part currently broken)

| Variable | Value | Why |
| --- | --- | --- |
| `VCB_ALT_EXTERNAL_API_ENABLED` | `true` | Master switch. Nothing calls an outside provider while this is false. |
| `VCB_ALT_ALPACA_API_KEY` | your new Alpaca Key ID | |
| `VCB_ALT_ALPACA_API_SECRET` | the matching Alpaca Secret Key | Must come from the **same** Alpaca account context as the key. A paper key with a live secret is the mismatch that caused the current failure. |
| `VCB_ALT_ALPACA_DATA_FEED` | `iex` | `iex` works on free plans. `sip` requires a paid subscription and returns 403 without one. |
| `VCB_ALT_INTRADAY_DATA_PROVIDER` | `alpaca` | Turns the live quote layer on. Leave as `none` until diagnostics pass in Step 3. |
| `VCB_ALT_DATA_PROVIDER` | `yahoo` | Daily price history. |
| `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA` | `true` | Fail closed. Do not set this to `false` in production. |
| `VCB_ALT_RESEARCH_DATA_PROVIDER` | `finnhub` | Fundamentals, news, short interest. |
| `VCB_ALT_FINNHUB_API_KEY` | your Finnhub key | |

### Production SaaS mode

The app refuses to boot in production mode unless **all** of these are set together.
That guard is intentional: a half-configured production mode is worse than none.

| Variable | Value |
| --- | --- |
| `VCB_ALT_DATABASE_URL` | your Neon PostgreSQL URL, ending in `?sslmode=require` |
| `VCB_ALT_USER_AUTH_ENABLED` | `true` |
| `VCB_ALT_USER_REGISTRATION_ENABLED` | `true` |
| `VCB_ALT_RATE_LIMIT_BACKEND` | `database` |
| `VCB_ALT_SCAN_QUEUE_ENABLED` | `true` |
| `VCB_ALT_WORKER_CRON_ENABLED` | `true` |
| `VCB_ALT_WORKER_TOKEN` | a long random value, 32+ characters |
| `CRON_SECRET` | **exactly the same value** as `VCB_ALT_WORKER_TOKEN` |
| `VCB_ALT_ALLOW_QUERY_TOKEN_AUTH` | `false` |
| `VCB_ALT_TRUSTED_PROXY_HEADERS` | `true` |
| `VCB_ALT_GLOBAL_OPERATOR_EMAILS` | your email address |
| `VCB_ALT_PRODUCTION_SAAS_MODE` | `true` |

**Expected result:** every variable above is present in the Production scope.

---

## Step 2 — Redeploy

Environment variables only take effect on a new deployment.

In Vercel, open the project's **Deployments** tab and redeploy the latest commit on
`main`. Note the deployment id (it looks like `dpl_...`) — you need it for the rollback in
Step 7.

Then check the app is alive. Replace `<YOUR-URL>` with the deployment URL:

```bash
curl -s https://<YOUR-URL>/api/health
```

**Expected result:**

```json
{"data": {"status": "healthy"}, "error": null, "message": "OK", "ok": true, "status_code": 200}
```

**If it fails:** open the deployment's Runtime Logs in Vercel. A missing variable from
Step 1 shows up as a startup error naming the variable.

### Confirm the deploy actually landed

A healthy `/api/health` only proves *a* build is running, not *this* build. On 2026-09-02
production answered every request correctly while serving code from before twenty-two
commits on `main` - four days of work, invisible from the outside.

Run this from the repository, on the commit you meant to deploy:

```bash
python tools/check_deploy.py https://<YOUR-URL>
```

**Expected result:**

```
  commit: deployed 1a2b3c4d5e6f, local 1a2b3c4d5e6f
  surface: 46 settings deployed, 46 in this checkout

deployment matches this checkout
```

**If it fails,** it prints which commit is live and which settings the deployed build has
never heard of. Redeploy and run it again. Do not continue through this runbook until it
passes: every step below tests behaviour that only exists in the newer code.

---

## Step 3 — Confirm Alpaca accepts the new credentials

This is the step that has been failing. Do it before anything else, because a live scan
cannot succeed while it fails.

The easiest way is in the browser: open the dashboard, find **Operations → Data
providers** in the left panel, and press **Test Alpaca credentials**.

**Expected result:** a green line reading *"Alpaca credentials work. Live market data is
available."*

**If it fails,** the panel names the problem and lists what to do. The classification
tells you which case you are in:

| Classification | Meaning | Fix |
| --- | --- | --- |
| `missing_config` | A variable from Step 1 is absent | Set it, redeploy |
| `key_context_mismatch_or_invalid` | HTTP 401. Key and secret are valid strings but not a working pair, or from different account contexts. **This is the current production failure.** | Regenerate the Key ID and Secret Key as one matching pair in one Alpaca account, update both variables, redeploy |
| `feed_forbidden` | HTTP 403. The account has no entitlement for the requested feed | Set `VCB_ALT_ALPACA_DATA_FEED` to `iex` |
| `rate_limited` | HTTP 429 | Wait for the Alpaca window to reset, then rerun |
| `trading_context_not_accepted` | The trading account was refused | Check whether the keys are Paper or Live and whether the account is active |
| `market_data_not_accepted` | Trading works, market data does not | Check Alpaca status, keep the scan fail-closed until `ready: true` |

The same check from a terminal, if you prefer:

```bash
curl -s "https://<YOUR-URL>/api/provider-diagnostics/alpaca" -H "Authorization: Bearer <ACCESS-TOKEN>"
```

Look for `"ready": true`. This endpoint never returns key values, so its output is safe
to read on screen — but it does make three live calls to Alpaca, so do not loop it.

**Do not continue until you see `ready: true`.** Everything after this depends on it.

---

## Step 4 — Confirm the configuration posture

```bash
curl -s "https://<YOUR-URL>/api/release-status" -H "Authorization: Bearer <ACCESS-TOKEN>"
```

**Expected result:** inside `configured_data`,

- `intraday_ready: true` ← this was `false` before Step 3
- `research_ready: true`
- `market_universe_live_ready: true`
- `database_backend: "postgresql"`
- `scan_queue_enabled: true`, `user_auth_enabled: true`, `worker_configured: true`
- `production_saas_ready: true`

`public_launch_ready` stays `false`, and that is correct. It is not a measure of whether
the scan works; it tracks the remaining launch gates listed in
[../RELEASE_DECISION.md](../RELEASE_DECISION.md) — legal review, monitoring, backup
drill. Do not treat this runbook as clearing those.

---

## Step 4b - Confirm the scan can actually reach a selection

Settings can all look right while the scan still selects nothing, because market data
alone reaches about 35/100 data coverage and 60 is required. Ask the app directly:

```bash
curl -s "https://<YOUR-URL>/api/config" -H "Authorization: Bearer <ACCESS-TOKEN>"
```

**Expected result:** inside `scan_pipeline`,

```json
"ready_for_selection": true,
"universe":   {"source": "watchlist", "ready": true},
"prefilter":  {"provider": "yahoo",   "ready": true},
"enrichment": {"source": "finnhub",   "ready": true}
```

**If it is false,** `blockers` names each missing stage and the setting that fixes it.
Locally the same check is `python -m vcb_alt doctor`.

This works without Alpaca. See
[MARKET_DATA_PROVIDERS.md](MARKET_DATA_PROVIDERS.md) for the full no-Alpaca preset.

---

## Step 5 — Run one real market scan

In production, pressing **Scan full market** does not scan immediately. It asks a
background worker for a fresh snapshot, and the dashboard waits and polls until the
worker finishes.

1. Open the dashboard and press **Scan full market / latest candidates**.
2. The status strip reads *waiting for worker* and the message counts attempts.
3. The daily cron runs the worker once a day, so on the first run trigger it yourself:

```bash
curl -s -X POST "https://<YOUR-URL>/api/admin/run-worker?limit=25" -H "X-VCB-Worker-Token: <WORKER-TOKEN>"
```

Note that production requires `POST` and rejects the token in the URL — both are
deliberate hardening, not a bug.

**Expected result:** within a minute the dashboard shows *"Market snapshot ready"*, the
candidate table fills with real tickers, and the selected set appears with allocation
percentages. **Scan freshness** reads *Fresh snapshot* and **Fail-closed state** no
longer shows a provider error.

**If candidates stay empty** while diagnostics pass, the scan ran but nothing cleared the
data-coverage threshold. Check **Operations → Data providers** for a provider marked
*Failing*: Finnhub enrichment is usually the missing piece, because price and volume
alone cannot reach the coverage the final selection requires.

Click any candidate to open its analysis page and confirm the five-year chart draws. That
proves the whole chain — universe, prefilter, enrichment, scoring, charting — is live.

---

## Step 6 — Run the hosted 1000-user gate

This is the last engineering gate before inviting anyone. It registers users, queues
scans, triggers the worker, polls jobs, reads snapshots and cleans up after itself.

**Run it from GitHub Actions, not from your machine.** Previous attempts from this
workstation stopped at preflight because the worker token was not available locally. The
workflow already has the secrets.

1. Add these repository secrets under **Settings → Secrets and variables → Actions**:
   `VCB_ALT_WORKER_TOKEN`, `CRON_SECRET`, `VCB_ALT_WEB_ACCESS_TOKEN` — the same values you
   set in Step 0 and Step 1.
2. Open **Actions → Hosted scan-heavy load test → Run workflow**.
3. Keep the defaults: 1000 users, concurrency 20. The provider-call guards exist to stop
   the run before it burns your daily provider budget.

**Expected result:** the run finishes green, and the report shows
`"load_test_passed": true`. That requires every one of: all 1000 flows succeeded, the
worker completed jobs, zero provider failures, zero worker failures, every snapshot read
succeeded, and every test account was cleaned up.

**If it reports `false`,** read `reason` in the output. A budget guard blocking the run is
not a failure of the app — it means the run would have exceeded the provider call
allowance you configured.

The equivalent local command, for reference only:

```bash
python tools/host_queue_load_test.py --base-url https://<YOUR-URL> --users 1000 --concurrency 20 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load --confirm-provider-budget
```

---

## Step 7 — Rollback

If any step leaves the deployment worse than before, roll back first and diagnose
afterwards. Rollback is a Vercel operation and takes under a minute.

1. Vercel → **Deployments**.
2. Find the last deployment that was healthy — the one from before Step 2.
3. Use **Promote to Production**.
4. Confirm with `curl -s https://<YOUR-URL>/api/health`.

To undo only the live-data change while keeping the deployment, set
`VCB_ALT_INTRADAY_DATA_PROVIDER` back to `none` and redeploy. The app returns to its
previous behaviour: no live quotes, no candidates, everything else working.

No database rollback is needed. Nothing in this runbook changes the schema.

---

## After go-live

Record the outcome in [../RELEASE_DECISION.md](../RELEASE_DECISION.md) — the deployment
id, the diagnostics result, whether the 1000-user gate passed. That file is what a future
reader trusts about the current state, and a successful scan is only meaningful if it is
written down with its date and deployment.

Remaining launch gates after this runbook, all tracked in that file: legal review of the
Terms, Privacy and Risk Disclosure drafts; external monitoring and alerting; the Neon
backup and restore drill; and email verification or OAuth for user accounts.

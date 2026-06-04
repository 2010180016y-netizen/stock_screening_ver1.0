# Operability Review

Review date: 2026-06-03 KST

Scope: production readiness, 1000-user public SaaS readiness, market-universe stock discovery correctness, removal candidates, and follow-up implementation prompts.

## 1. Final Operating Decision

NOT_READY_FOR_PUBLIC_1000_USER_SAAS.

The deployed service is configured as an owner-trial SaaS build with PostgreSQL, per-user auth, database-backed rate limits, scan queue settings, worker configuration, market-universe scan mode, Alpaca intraday/universe settings, and Finnhub research settings.

However, the core production scan path is not currently usable because `/api/user/scan` fails closed with:

```text
Alpaca rejected the market-universe request with HTTP 401. Check API key, secret, and data feed.
```

This means the product cannot truthfully be operated as a live all-market research-candidate service until the Alpaca credential/feed issue is fixed and the scan-heavy hosted load test passes with real provider calls.

## 2. Verified Current State

Production URL checked:

```text
https://stockscreeningver10.vercel.app
```

Production config highlights from `/api/config`:

- `scan_mode=market_universe`
- `database_backend=postgresql`
- `user_auth_enabled=true`
- `rate_limit_backend=database`
- `scan_queue_enabled=true`
- `worker_configured=true`
- `worker_cron_enabled=true`
- `data_provider=yahoo`
- `intraday_data_provider=alpaca`
- `research_data_provider=finnhub`
- `market_scan_requires_live_data=true`

Production readiness highlights:

- `/api/release-status` returns `public_launch_ready=false`.
- `/api/saas-readiness` returns `decision=NOT_READY_FOR_1000_USER_SAAS`.
- `/api/saas-readiness` reports `ready_for_1000_users=false` and `p0_blocker_count=6`.
- A real authenticated `/api/user/scan` smoke failed with Alpaca `HTTP 401`.

## 3. Current Usable Range

Safe for:

- Operator-only dashboard access.
- Configuration/status verification.
- Auth/session and tenant-control smoke testing.
- Non-public QA of detail pages and enrichment behavior.
- Internal debugging of provider credentials, scan queue, logs, and rate limits.

Not safe for:

- Unrestricted external release.
- 1000 concurrent/active user marketing.
- User-facing claim that the app scans the live market and returns current best candidates.
- Paid usage.
- Investment-advice-like positioning.

## 4. P0 Blockers

1. Alpaca live market-universe scan fails with `HTTP 401`.
   - Impact: core product flow does not produce live market-wide research candidates.
   - Required fix: correct Alpaca key/secret/feed/account context, then run live scan smoke and hosted queue load test.

2. Release documents contain stale external-readiness language.
   - Impact: docs overstate readiness versus current deployed behavior.
   - Required fix: update `RELEASE_DECISION.md`, `QA_REPORT.md`, external-readiness text, and operator docs to state that unrestricted external release is blocked.

3. Legal/provider licensing review is incomplete.
   - Impact: public stock candidate-output service can create regulatory, licensing, and user-risk exposure.
   - Required fix: counsel-reviewed Terms, Privacy, Risk Disclosure, provider-license confirmation, and no-investment-advice UX language.

4. Hosted scan-heavy load test is not valid until live provider scan succeeds.
   - Impact: previous health/control-plane load tests do not prove scan path capacity.
   - Required fix: run 1000-user queue completion load test with worker trigger, provider quota monitoring, and failure budget.

5. Monitoring and alerting are not connected to an external incident channel.
   - Impact: provider failures, worker failures, queue backlog, and database errors may be missed during operation.
   - Required fix: central logs, metrics, alert thresholds, webhook/email/PagerDuty-style notification, and runbook.

6. Auth hardening remains partial.
   - Impact: per-user auth exists, but public SaaS expectations require email verification/OAuth, admin MFA, stronger RBAC, and abuse handling.
   - Required fix: implement auth provider or hardened first-party auth with email verification, MFA for admins, role checks, and tests.

## 5. P1 Gaps

1. Queue worker needs production observability, retry policy, dead-letter handling, and stale-running recovery evidence.
2. Neon backup/restore drill has a plan but lacks completed restore evidence.
3. Tenant isolation is tested locally but still needs deployed cross-tenant access tests for admin/export/delete flows.
4. Provider outage and provider budget tests need to be run against staging/hosted infrastructure.
5. UI still contains manual watchlist/starter-watchlist copy and behavior that conflicts with the market-wide discovery product direction.
6. Korean/English separation needs a final pass so Korean mode translates all non-ticker/non-company UI strings.
7. Explanation summary is template-based by default; wording must not imply a language model selects stocks. OpenAI, when active, explains deterministic scoring output only.
8. Live-provider contract tests are missing from CI/staging.
9. Support, incident, and abuse-response workflows are not production-ready.

## 6. P2/P3 Gaps

1. Detail charts are useful but not a true streaming chart experience.
2. Provider coverage scoring should be visible enough for users to know when fundamentals/news/options/short data are missing.
3. Admin dashboards can be improved for provider spend, quota, queue latency, and failed scans.
4. Paid-plan, billing, and subscription gating are intentionally absent and should stay out until legal/support posture is ready.

## 7. Remove Or Demote Before Unrestricted External Release

- Remove stale external-readiness language from release docs.
- Remove or hard-gate sample/demo fallback from production candidate-output paths.
- Remove starter watchlist seeding as a primary product behavior; keep watchlists only as optional research lists.
- Demote manual ticker input from the main CTA because the intended product is all-market discovery.
- Hide or disable legacy global `/api/watchlist`, `/api/scan`, and `/api/select` paths in SaaS mode.
- Remove wording that implies generated summary text makes the stock-selection decision when the current selector is deterministic scoring plus template explanation.
- Remove old screenshots/docs that show fixed sample picks as if they were live research candidates.
- Remove unreviewed legal, privacy, and risk language from public marketing pages until counsel approves it.

## 8. Improvement Priority

### P0-1. Restore Live Market Scan

Goal: authenticated production scan returns real market-universe candidates from Alpaca snapshots and Finnhub enrichment.

Prompt:

```text
Read the entire stock_screening_ver1.0 repo and focus on the market-universe scan path. Fix the production Alpaca HTTP 401 issue without weakening fail-closed behavior. Verify Key ID, Secret Key, paper/live endpoint selection, market data feed, assets endpoint fallback, stock snapshots endpoint, and Vercel env names. Add a provider credential diagnostics endpoint that verifies credentials without exposing secrets. After changes, run local tests, deploy, and prove /api/user/scan returns real market_universe candidates with universe/prefilter metadata and no sample fallback.
```

### P0-2. Correct Release Truth

Goal: all docs and public status match actual readiness.

Prompt:

```text
Audit README.md, RELEASE_DECISION.md, QA_REPORT.md, OPERATIONS.md, DEPLOYMENT.md, PUBLIC_DEPLOYMENT.md, web UI copy, and readiness endpoints. Remove stale external-readiness claims and update the product state to owner-trial only until live scan, legal review, monitoring, auth hardening, backup restore, and hosted scan-heavy load tests pass. Preserve historical notes clearly as historical, not current status.
```

### P0-3. Make Scans Worker-Owned

Goal: users read fresh shared scan results instead of triggering heavy provider scans per click.

Prompt:

```text
Refactor market-universe scans so production user requests enqueue or read the latest durable scan snapshot. The worker should own Alpaca/Finnhub provider calls, write scan_reports and selected candidates to PostgreSQL, expose status/freshness, and return cached fresh results instantly to users. Add retry, stale-running recovery, dead-letter status, and tests for concurrent 1000-user reads during a scan.
```

### P0-4. Provider Outage And Budget Controls

Goal: provider failures degrade safely and visibly.

Prompt:

```text
Implement provider circuit breakers, quota counters, request budgeting, timeout/retry policy, and operator-visible provider health for Alpaca, Finnhub, Yahoo, SEC, and OpenAI/template summaries. Add tests that simulate Alpaca 401, 429, timeout, malformed JSON, Finnhub quota exhaustion, and Yahoo outage. Ensure production fails closed for final candidate output when required live data is unavailable.
```

### P1-1. Hosted Scan-Heavy Load Test

Goal: prove 1000-user operation on the real hosted scan path.

Prompt:

```text
Create and run a hosted scan-heavy load test that registers/logs in test users, enqueues scan jobs, triggers the protected worker endpoint, polls job completion, measures p50/p95/p99 latency, queue depth, provider calls, database errors, 4xx/5xx rates, and selected candidate freshness. Test at the 1000-user target with real provider limits respected. Write results to QA_REPORT.md and update RELEASE_DECISION.md.
```

### P1-2. Monitoring And Incident Runbooks

Goal: operator can detect and respond to production failures.

Prompt:

```text
Connect production monitoring for request errors, queue backlog, worker failures, provider failures, database errors, auth abuse, and rate-limit saturation. Add alert thresholds, webhook/email notification, request IDs, redacted structured logs, and runbooks in OPERATIONS.md. Verify alerts with controlled provider-failure and worker-failure tests.
```

### P1-3. Auth, MFA, RBAC, Privacy

Goal: public SaaS account boundary is defensible.

Prompt:

```text
Implement production-grade per-user auth hardening: verified email or OAuth, admin MFA, role-based authorization on admin/export/delete/queue endpoints, session rotation, password reset, account deletion, data export, audit events, and abuse controls. Add tenant-isolation tests and deployed API smoke tests proving users cannot access another tenant's data.
```

### P1-4. Backup And Restore Drill

Goal: prove recoverability.

Prompt:

```text
Execute a Neon PostgreSQL backup/restore drill in staging. Document backup schedule, restore target, migration drift check, data integrity checks, RTO/RPO, rollback steps, and evidence. Add a lightweight recurring restore-check procedure to OPERATIONS.md and update QA_REPORT.md with results.
```

### P1-5. UI Product Direction Cleanup

Goal: the app looks and behaves like all-market discovery, not manual watchlist scoring.

Prompt:

```text
Read the current web UI and product docs. Redesign the dashboard hierarchy so the primary action is market-wide discovery. Demote manual watchlists to optional research lists, remove starter-watchlist behavior from the main experience, expose scan freshness/source/provider coverage, and ensure Korean mode translates every UI string except ticker/company names. Verify responsive layout, no text overflow, and browser smoke on mobile and desktop widths.
```

### P2. Optional OpenAI Explanation Summary Layer

Goal: Generated summaries explain but do not choose stocks.

Prompt:

```text
Add an optional OpenAI summary provider that explains deterministic scoring inputs, provider coverage, risks, catalysts, and missing data for each selected ticker. Keep final stock selection deterministic and auditable. Add env-based enablement, prompt templates, redaction, caching, timeout fallback to template summaries, and tests proving no candidate is returned solely because of generated summary text.
```

## 9. Current Next Step

The first required update is not more UI work. The first required update is fixing Alpaca live credential/feed validation and proving that production `/api/user/scan` returns live all-market candidates without sample fallback.

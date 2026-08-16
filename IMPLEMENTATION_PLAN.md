# Implementation Plan

## 2026-06-10 Public 1000-User SaaS Blocker Closure Plan

### Current P0/P1/P2 Findings

P0:

- Production all-market discovery is still blocked unless Alpaca/Finnhub/Yahoo live-data credentials and permissions are valid. Live-data-required mode must continue to fail closed instead of returning sample/demo candidates.
- User-facing scan requests must not execute provider-heavy market scans. They must read a fresh durable `market_scan_snapshot` or enqueue/status only; the protected worker must be the only provider-heavy execution owner.
- Hosted 1000-user readiness is not proven until the secret-backed CI/operations runner records `load_test_passed=true`, worker completion, snapshot reads, provider call delta, queue depth, provider failure handling, and `db_error_count=0`.

P1:

- Provider alert visibility must distinguish tenant admin from global operator data. Tenant admins should not see cross-tenant/global provider operations unless explicitly granted a global operator role.
- Production token handling should not accept shared access or worker secrets through query strings.
- IP rate limiting must only trust `X-Forwarded-For` from configured trusted proxy mode; otherwise use the direct client address.
- Request JSON parsing needs a production body-size cap and invalid-JSON `400` responses.

P2:

- Dashboard/detail HTML, CSS, JS, and served Korean i18n need an extracted asset path so runtime UI is not dependent on the large embedded fallback constants in `web.py`.
- Mobile and Korean/English UI smoke checks need an executable test so regressions are caught before deployment.

### Implementation Scope

1. Add config switches for trusted proxy headers, production query-token allowance, request body byte limit, and global operator roles.
2. Harden `/api/admin/run-worker` to require `POST` in production SaaS and reject query-string worker tokens unless explicitly allowed outside production.
3. Keep public web query-token cookies only for non-production/operator trial; production SaaS should use session/header auth and must not mint cookies from URL tokens.
4. Change market-universe tenant scan jobs so they never call `scan_market_universe` inline; they return a queued/pending status if no fresh worker snapshot exists.
5. Add tenant/global filtering for provider alerts and store optional tenant metadata without exposing secrets.
6. Extract dashboard/detail/login/legal HTML, CSS, and served JS into `vcb_alt/web_assets/` and load those UTF-8 files first, keeping embedded constants only as a fallback.
7. Replace broken Korean test expectations with valid UTF-8 checks and add served JS/mobile CSS smoke assertions.
8. Update QA, release, operations, and changelog with the exact verified and still-blocked gates.

### Verification Plan

- `python -m unittest discover -s tests`
- `python -m tools.lint`
- `python -m tools.typecheck`
- `python -m compileall -q vcb_alt tests tools api`
- local web health/config/served JS smoke
- served JS encoding and Korean text check
- responsive CSS smoke or in-app/browser smoke where tool/runtime is available
- hosted load-test workflow dispatch if GitHub/runner secrets are accessible; otherwise record the exact secret-backed blocker.

## 2026-05-26 Market-Universe Algorithm Correction

### Problem

The implemented scan path evaluated user-entered watchlist symbols. That does not match the intended product: a market-wide stock discovery system that scans real US equities, scores the strongest current opportunities, and recommends the highest-confidence candidates.

### Implementation Direction

1. Make `VCB_ALT_SCAN_MODE=market_universe` the product default while keeping `watchlist` as a legacy/manual mode.
2. Load the market universe from Alpaca active US-equity assets when API credentials are configured.
3. Support `data/universe.csv` as an operator-controlled fallback universe and sample data only as an explicit non-live fallback.
4. Use Alpaca multi-symbol stock snapshots as the fast live/near-live prefilter layer.
5. Rank the full universe by intraday change, relative volume, dollar liquidity, and spread.
6. Cache the completed market scan report for the intraday TTL so concurrent users reuse fresh results instead of creating provider-call storms.
7. Enrich the top prefilter names with Finnhub or operator CSV research data.
8. Run the existing seven-archetype scoring engine and data-coverage gate over the enriched candidates.
9. Select up to three final candidates with existing portfolio constraints.

### Files Updated

- `vcb_alt/config.py`: scan-mode and market-universe configuration.
- `vcb_alt/market_universe.py`: new universe loading, Alpaca snapshot prefiltering, candidate normalization, and market scan result orchestration.
- `vcb_alt/scoring.py`: intraday Alpaca momentum support and market-data coverage recognition.
- `vcb_alt/web.py`: dashboard scan/select endpoints now use market-universe mode when configured.
- `vcb_alt/job_queue.py`: background workers can process market-universe scans.
- `vcb_alt/cli.py`: CLI scan/select honor the configured scan mode.
- `.env.example`: market-universe environment variables.
- `data/universe.example.csv`: operator universe template.
- `tests/test_market_universe.py`: regression coverage for sample fallback and cached Alpaca prefilter flow.

### Remaining Production Requirement

Production must set `VCB_ALT_EXTERNAL_API_ENABLED=true`, `VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca`, Alpaca credentials, `VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub` or `finnhub_csv`, and preferably `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true` so sample fallback cannot be mistaken for live research candidate output.

Current status note, 2026-05-19: this was the initial implementation plan for converting a documentation-only repository into a runnable MVP. The implemented system has since advanced to a token-protected owner/operator-trial web dashboard with automatic EOD market data and a decision-first UI. For the current architecture, read `research.md`. For input-based paging, read `plan.md`. For the current external-release blockers, read `SAAS_IMPLEMENTATION_PLAN.md`.

## 0.13. 2026-05-24 Algorithm Review And Korean Localization

User request:

- Review the stock-selection algorithm from beginning to end and explain it.
- Fix English/Korean mode separation so the Korean version is translated except ticker/company names.

Implemented scope:

- Added `ALGORITHM_REVIEW.md` documenting the provider snapshot, scoring, data-coverage gate, and final portfolio selection process.
- Improved portfolio tie-breaking so equal combined scores prefer higher data coverage before volatility, sizing, and ticker tie-breaks.
- Added Korean dynamic translation helpers for dashboard and ticker detail pages.
- Translated Korean-mode display for archetype labels, public review labels, rationale bullets, precision notes, warnings, coverage labels, data source names, explanation summary sections, and expert consensus copy.
- Kept ticker symbols and company/security names unchanged.
- Added tests for Korean dynamic translation availability and the data-coverage tie-break.

Verification:

- Lint passed: `lint ok (40 files)`.
- Typecheck passed: `type hints ok (308 objects)`.
- Tests passed: `56`.
- Served dashboard/detail JavaScript passed `node --check`.
- Compile/build passed.

## 0.12. 2026-05-24 SaaS Dashboard Scan Button Recovery

User issue:

- Clicking `Run scan` in the deployed dashboard did not show stock candidates.

Root cause:

- Production runs with per-user SaaS auth enabled.
- The dashboard still called legacy global `/api/scan` and `/api/select` for the button flow.
- Those legacy endpoints are intentionally blocked in SaaS mode, so the UI could not complete a tenant-scoped scan even though the lower-level scoring engine still worked.

Implemented scope:

- Added authenticated tenant endpoints `POST /api/user/scan` and `POST /api/user/select`.
- Updated dashboard JavaScript to choose tenant endpoints when `user_auth_enabled=true`.
- Added browser-scoped automatic tenant registration/login and stale-session recovery.
- Added starter watchlist seeding for first-run demo tenants.
- Changed `Run scan` to render final selection from the scan response when present, avoiding a second API call before candidates appear.
- Batched tenant evaluation persistence into one commit per scan for faster small-watchlist scans.
- Added code comments documenting the synchronous tenant scan path and batched commit optimization.
- Added regression tests locking the SaaS auth API scan/select flow and dashboard endpoint wiring.

Verification:

- Lint passed: `lint ok (40 files)`.
- Typecheck passed: `type hints ok (307 objects)`.
- Tests passed: `55`.
- Served dashboard/detail JavaScript passed `node --check`.
- Local SaaS API smoke scanned `7` tickers and selected `3`.
- Production SaaS API smoke scanned `7` tickers in `69ms` and selected `PLTR`, `VST`, `MSTR`.
- In-app browser button test passed: `Run scan` showed `Scan completed in 21 ms` and rendered candidate rows/cards.
- Production deploy: `dpl_EJwfpEvi9SnziMreYcbGAMeyVKGR`.
- Hosted health smoke after deploy passed: `100/100` HTTP `200`, p95 `955.29ms`.

Remaining:

- This fixes the interactive dashboard scan path. Continue using queue-backed scans for hosted 1000-user load and large watchlists.
- Keep OAuth/email verification, admin MFA, external monitoring, backup/restore drill, and legal review as public SaaS launch controls.

## 0.8. 2026-05-22 Expert Re-Read, Accuracy, And Speed Gate

User request:

- Re-read the system from end to end with expert review, update comments/planning documents, optimize speed and selection accuracy, and run the product.

Implemented scope:

- Fixed PostgreSQL session authentication so `TIMESTAMPTZ` values returned by psycopg do not crash authenticated requests.
- Made PostgreSQL queue claiming atomic with `FOR UPDATE SKIP LOCKED ... RETURNING` while preserving the SQLite fallback path.
- Added PostgreSQL advisory locking to the database-backed rate limiter so concurrent requests share a real per-bucket limit.
- Persisted tenant scan results into `tenant_evaluations` so queued scans leave auditable per-user evaluation history, not only transient job JSON.
- Made operation/export JSON decoding handle PostgreSQL JSON/datetime objects as well as SQLite strings.
- Changed Yahoo/Stooq process cache to include a TTL bucket so long-lived workers do not serve market data past the configured cache window.
- Updated docs/readiness state to reflect Neon PostgreSQL cutover, worker endpoint/Cron, and hosted health-load smoke while keeping scan-heavy load tests as a blocker.

Validation plan:

- Run targeted auth/DB/provider tests first.
- Run lint, type checks, full unit tests, compile/build, release preflight, and local app startup.
- If production credentials remain configured, run a safe release-status/protected smoke check without printing secrets.

Remaining external-release blockers:

- Scan-heavy hosted queue load testing against PostgreSQL.
- Provider outage and budget tests.
- Centralized monitoring/alerts and Neon backup/restore drill.
- OAuth/email verification, MFA/RBAC, WAF hardening, and legal-reviewed launch docs.

## 0.9. 2026-05-22 Historical External-Release Gate Tooling

User request:

- Proceed with scan-heavy hosted queue load test, provider outage/budget test, OAuth/MFA/RBAC, monitoring/alerts, Neon backup/restore drill, and legal review.

Implemented scope:

- Added `tools/host_queue_load_test.py` to exercise hosted registration, login/session, tenant watchlist, scan job enqueue, optional worker trigger, and job polling.
- Added `tools/provider_resilience_test.py` to simulate provider outage/budget exhaustion and prove scan/select returns structured provider failures instead of crashing.
- Added `tools/ops_health_report.py` to collect redacted health, release, provider, and SaaS readiness status, with optional webhook alerting.
- Added `tools/queue_load_test.py` for local queue-backed 1000-user scan simulation.
- Added per-user export/delete APIs, tenant admin users/audit/queue-status APIs, audit event storage, and stale scan-job recovery.
- Added `AUTH_MFA_RBAC_PLAN.md` with launch RBAC matrix and MFA/OAuth implementation requirements.
- Added `MONITORING_ALERTING_PLAN.md` with dashboard and alert thresholds.
- Added `NEON_BACKUP_RESTORE_DRILL.md` with staging-first restore drill and evidence checklist.
- Added `LEGAL_REVIEW_PACKET.md` with counsel-facing review questions and official SEC/FINRA reference links.

Verification:

- Provider resilience simulation passed locally.
- Hosted health smoke passed for `100` requests at concurrency `10`.
- Hosted queue smoke registered `3` users and queued `3` scan jobs; jobs remained queued because no worker token was available to manually trigger the worker.
- Local queue-backed 1000-user simulation passed with `1000` completed jobs, `30000` tenant evaluations, and `0` failures.
- Lint, typecheck, `52` tests, and compile/build passed.

Remaining:

- Full scan-heavy hosted completion test requires `VCB_ALT_WORKER_TOKEN` to be available to the test runner or a shorter production worker schedule.
- Neon backup/restore drill requires operator-side Neon console/API action on a staging branch.
- Legal review requires qualified counsel signoff.

## 0.10. 2026-05-22 Production 1000-User Hardening Follow-Up

Finding:

- Post-deploy hosted smoke found intermittent production `500` responses during concurrent cold starts.
- Vercel logs traced the failure to PostgreSQL `audit_events_id_seq` creation racing across serverless workers during SaaS schema initialization.

Implemented scope:

- Serialized PostgreSQL SaaS schema initialization with `pg_advisory_xact_lock(...)`.
- Split the Vercel `/api/health` path so health checks load configuration only and do not execute database DDL.
- Added regression coverage for the PostgreSQL SaaS schema advisory lock.
- Updated QA, changelog, and SaaS planning docs with the production failure mode and remediation.

Verification plan:

- Rerun lint, typecheck, full tests, local direct 1000-user simulation, local queue-backed 1000-user simulation, provider resilience, production deployment, hosted health load, and hosted queue smoke.

Remaining:

- Hosted queue completion at public-launch scale still requires worker-trigger access or scheduled worker capacity evidence.
- OAuth/email verification, admin MFA, monitoring alerts, Neon restore drill, and legal signoff remain public-launch gates.

## 0.11. 2026-05-24 1000-User Production Completion Gate

Implemented scope:

- Split durable rate-limit buckets by endpoint class so signup/auth bursts, authenticated tenant APIs, and protected worker calls do not block each other.
- Updated hosted queue load tooling with `--worker-limit`, staged error reporting, and `--simulate-distributed-ips`.
- Added served JavaScript i18n replacement for dashboard/detail pages so Korean UI assets remain syntactically valid even if historical embedded strings are corrupted.
- Documented endpoint-specific SaaS rate-limit environment variables in `.env.example`.

Verification:

- Lint passed: `40` files.
- Typecheck passed: `305` objects.
- Tests passed: `55`.
- Served dashboard/detail JavaScript passed `node --check`.
- Local queue-backed 1000-user simulation completed `1000` jobs and `30000` evaluations with `0` errors.
- Hosted production worker-triggered 1000-user test completed `1000/1000` jobs with `0` errors on deployment `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`.
- Post-run production health passed `300/300` HTTP `200` with `0` errors.

Remaining:

- Email verification/OAuth, admin MFA, external monitoring/alerts, Neon restore drill, and legal review are still required before paid or regulated launch, but the technical 1000-user queue completion gate is closed.

## 0.7. 2026-05-21 1000-User SaaS Readiness Gate

User request:

- Move beyond owner trial blockers by implementing production PostgreSQL support, per-user auth, tenant isolation, durable rate limiting, queue-backed scans, and actual deployment load-test tooling.

Implemented scope:

- Add optional PostgreSQL runtime adapter selected by `VCB_ALT_DATABASE_URL=postgresql://...`.
- Extend PostgreSQL migration with `rate_limit_events` and `scan_jobs`.
- Add `VCB_ALT_PRODUCTION_SAAS_MODE=true` startup guard that requires PostgreSQL, per-user auth, database rate limiting, and scan queue together.
- Add `VCB_ALT_RATE_LIMIT_BACKEND=database` so request limits persist across processes/serverless instances.
- Add `VCB_ALT_SCAN_QUEUE_ENABLED=true`, tenant scan-job APIs, and `python -m vcb_alt worker run-once`.
- Block legacy global watchlist/scan/select APIs when per-user auth is enabled.
- Add local and hosted load-test tools.

Verification completed:

- Unit test suite expanded to `43` tests and passed.
- Local SaaS smoke flow passed: register user, add tenant watchlist, enqueue scan job, run worker, complete job.
- Local 1000-user / 30,000-evaluation simulation passed with `0` errors and tenant isolation passed.

Deployment status after 2026-05-22 cutover:

- Neon PostgreSQL is connected in Vercel Production.
- Production SaaS mode is enabled and reports PostgreSQL, per-user auth, database rate limiting, scan queue, worker token, and worker cron as configured.
- Production SaaS smoke passed for registration, tenant watchlist, scan queue, protected worker processing, and job status lookup.
- Hosted `/api/health` load smoke passed after cutover with `1000/1000` HTTP 200 responses and `0` errors.
- Remaining launch work is scan-heavy queue/provider load testing, monitoring, backup/restore, auth hardening, WAF, and legal review.

## 0. 2026-05-19 Historical External-Release Gate Update

The latest production deployment at `https://stockscreeningver10.vercel.app` now renders the dark decision-first screening workspace with real API data, final candidate cards, actionable/excluded groupings, provider status, and score-detail modals.

Historical note: this entry described a controlled evaluation gate, not current launch approval. Before moving beyond owner/operator trial, the next implementation pass must keep the current product direction intact:

- Preserve VCB-Alt as a decision-support screening desk, not a generic filter-heavy screener.
- Keep automatic trading out of scope.
- Reduce legal/advice ambiguity by using SaaS-safe public labels in the UI while preserving raw audit fields in API data.
- Expose provider and scoring-version status so users and operators can tell what produced each result.
- Add starter Terms, Privacy, and Risk Disclosure documents as operational placeholders pending legal review.
- Keep token-protected access until per-user auth, tenant isolation, durable storage, and load testing exist.

## 0.1. 2026-05-19 Candidate Explanation And Detail Page Gate

Before the next deployment, the UI must explain not only which tickers were selected, but why each ticker was selected.

Expert consensus for the detail page:

- Product/UX: show a short reason on the card and put deeper analysis behind a click so the first screen stays decision-first.
- Quant/Engineering: include score, scoring version, trend metrics, risk reference, and the exact rationale list used by the engine.
- Market-data/Ops: include a recent five-year price/volume chart when the provider supports it, and label the data freshness honestly.
- Security/Compliance: do not label end-of-day provider data as true real-time unless the provider explicitly supports streaming or intraday freshness.
- Domain/PM: always show sector/industry, selection reason, current status, data source, and limitations.

Implementation scope:

- Add `/ticker/<ticker>` detail page route.
- Add `/api/ticker-analysis?ticker=<ticker>` API route.
- Add five-year chart data from the active provider where available.
- Add sector/industry profile enrichment with safe fallback.
- Update candidate cards and tables so clicking navigates to the detail page.
- Add tests for the detail route, API, chart data, industry display, and selection rationale.

Out of scope for this gate:

- True streaming/tick-by-tick real-time market data.
- Paid or licensed production data vendor integration.
- Brokerage actions or order placement.

## 0.2. 2026-05-19 Responsive And Bilingual UI Gate

Before the next deployment, the dashboard and ticker detail page must behave like a public web product across desktop, mobile, and browser zoom.

Expert consensus for this UI pass:

- UX/Product: preserve the decision-first VCB-Alt workflow while making cards, tables, and detail panels readable on mobile.
- Frontend Engineering: keep the no-build HTML/CSS/JS architecture and use responsive CSS rather than adding framework complexity.
- Accessibility/QA: prevent text overflow with wrapping guards, stable card dimensions, readable contrast, and mobile table labels.
- Localization/Product: add a user-selectable Korean/English mode and persist the preference locally.

Implementation scope:

- Add EN/KR language toggles to the dashboard and ticker detail page.
- Re-render dynamic scan, selection, operations, and detail labels after a language change.
- Use an app-standard system font stack including Inter, Segoe UI, Roboto, Noto Sans KR, and Apple SD Gothic Neo.
- Add `min-width: 0`, wrapping, button line-height, and mobile table-card safeguards so text stays inside boxes.
- Make the ticker chart responsive with an aspect ratio and mobile height floor.

Out of scope for this gate:

- Server-side locale negotiation.
- Full translation of provider-supplied market-data notes or raw scoring phrases.
- Replacing the no-build frontend with React/Vue/Svelte.

## 0.3. 2026-05-20 Data Quality Gate

User correction:

- Price charts alone do not match the intended VCB-Alt product direction.
- Automatic EOD chart data may support market context, but final selection must require broader data quality.

Expert consensus for this gate:

- Product/PM: keep VCB-Alt as a precision screening desk, not a chart-only momentum picker.
- Quant: price/volume factors can contribute to setup timing, but final selection needs market, fundamental, catalyst, and positioning coverage.
- Data Engineering: add a manual enrichment overlay now, then replace it with licensed/provider-backed feeds later.
- Compliance: if enrichment is missing, block final-selection language instead of implying a research-complete candidate.

Implementation scope:

- Add `data/enrichment.csv` support for operator-verified fundamentals, catalysts, short/options, insider, float, and related fields.
- Apply enrichment over Yahoo/Stooq EOD price/volume snapshots before scoring.
- Add a data coverage score from four groups: market price/volume, fundamentals/earnings, catalyst/news, and positioning.
- Block final entry selection when data coverage is below `60/100`, even if technical score is high.
- Surface data coverage in evaluation results and detail-page metrics.
- Add tests proving price-only Yahoo/Stooq output is blocked and enriched Yahoo output can pass.

Out of scope for this gate:

- Claiming live real-time or AI-driven judgment.
- Using unverified scraped fundamentals as production truth.
- Integrating paid vendor credentials without explicit operator approval.

## 0.4. 2026-05-20 Research Data Provider Gate

User correction:

- The system needs a real structure for fundamentals, news, short interest, options, and earnings-surprise data, not only manual CSV enrichment.

Implementation scope:

- Add a separate research-data provider layer beside the market-data provider.
- Support `VCB_ALT_RESEARCH_DATA_PROVIDER=csv`, `finnhub`, and `finnhub_csv`.
- Add `VCB_ALT_FINNHUB_API_KEY` and research-data cache TTL configuration.
- Fetch or cache fundamentals, earnings surprise, recent news catalysts, insider transactions, short interest, and option-chain open interest when Finnhub is configured.
- Keep the safe default as `csv`, so no paid/external research API is called without explicit configuration.
- Let `finnhub_csv` apply Finnhub first and operator CSV overrides second.
- Add tests using local Finnhub cache fixtures so CI does not require network or credentials.

Risk controls:

- Missing API keys produce provider-status warnings and do not crash scans.
- Failed research calls return empty enrichment and leave data coverage below the selection gate.
- API keys stay in environment variables and are never returned by provider status.

## 0.5. 2026-05-20 Full Data + Explanation Summary Layer

Goal:

- Preserve the VCB-Alt decision-support workflow while adding the data layers users expect from a serious stock screener: near-real-time quote, fundamentals, earnings, news/disclosures, analyst trend, short interest, options, and explanation summaries.

Implementation scope:

- Add `VCB_ALT_INTRADAY_DATA_PROVIDER=none|alpaca` with Alpaca credentials, feed, and short TTL cache.
- Keep Yahoo/Stooq as daily chart and technical engines; add Alpaca only as a quote/snapshot overlay so missing live data cannot break the scan.
- Extend Finnhub enrichment with analyst rating trend parsing.
- Add optional SEC submissions metadata via `data.sec.gov` for latest filing type/date/URL and a 30-day filing catalyst flag.
- Add `VCB_ALT_AI_SUMMARY_PROVIDER=template|openai`; use deterministic template summaries by default and call OpenAI Responses API only when explicitly configured for explanation summaries.
- Surface explanation summary, intraday quote, short interest, option put/call ratio, and analyst score on ticker detail pages.

Risk controls:

- No paid or credentialed provider is called unless the corresponding provider is explicitly enabled and credentials are present.
- API keys are not returned by provider status, logs, or UI.
- Failed Alpaca/Finnhub/SEC/OpenAI calls degrade to missing context or template fallback, not a 500.

Tests:

- Local cache fixtures verify Alpaca snapshot, Finnhub research/analyst data, SEC filings, and template explanation summary without network or credentials.

## 0.6. 2026-05-21 Operator Trial Stabilization

Goal:

- Make the owner trial build smoother and safer before broader user exposure.

Implementation scope:

- Re-read the runtime flow from Vercel entrypoint through web routes, provider enrichment, scoring, detail pages, and documents.
- Remove duplicate ticker snapshot loading from `/api/ticker-analysis` by passing the already-enriched snapshot into `get_ticker_profile`.
- Cache the serverless bootstrap configuration after the first warm-process request so Vercel does not re-run setup on every request.
- Harden public access-token cookies by adding the `Secure` attribute when Vercel forwards HTTPS traffic.
- Keep Alpaca disabled for the practical owner trial if credentials still return HTTP 401; keep Finnhub enabled because it is verified and improves data coverage.

Validation:

- Unit tests cover secure cookie behavior and snapshot reuse-compatible profile loading.
- Local and production smoke checks must verify release status, provider status, ticker analysis, scan/select, and no secret leakage.

## 1. Current State Summary

The repository is a product specification bundle with no runnable application. The highest-value path is to preserve the local-first Phase 1 scope and implement a conservative Python CLI MVP that supports initialization, watchlists, deterministic stock evaluation, scans, logs, failed-job inspection, and data deletion.

## 2. Improvement Goal

Turn the documentation-only repo into an installable, testable, local production baseline suitable for private beta use by one operator.

## 3. P0 Resolution Plan

- Add Python package skeleton under `vcb_alt/`.
- Add `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`.
- Add SQLite schema creation and DB helper functions.
- Add CLI with `init-db`, `doctor`, `watchlist`, `evaluate`, `scan`, and `admin` commands.
- Add validation and safe exception handling.
- Add deterministic sample data provider.
- Add tests for validation, DB, evaluation, scan, and CLI behavior.
- Add README/SETUP/DEPLOYMENT/TESTING/OPERATIONS docs.

## 4. P1 Resolution Plan

- Add redacted logging and failed-job capture.
- Add unified result envelope for command success/failure.
- Add safe defaults for external APIs and rate-limit placeholders.
- Add local data export/delete flow.
- Add CHANGELOG, QA_REPORT, RELEASE_DECISION.
- Clearly document no auto-trading and no investment-advice guarantee.

## 5. Files To Modify

- None of the original spec files will be rewritten in this pass because they are source context and contain encoding damage. New operational docs will supersede them for execution.

## 6. Files To Create

- `ASSUMPTIONS.md`
- `AUDIT_REPORT.md`
- `PRODUCT_REQUIREMENTS.md`
- `USER_FLOWS.md`
- `RELEASE_CRITERIA.md`
- `IMPLEMENTATION_PLAN.md`
- `README.md`
- `SETUP.md`
- `DEPLOYMENT.md`
- `TESTING.md`
- `OPERATIONS.md`
- `CHANGELOG.md`
- `QA_REPORT.md`
- `RELEASE_DECISION.md`
- `.env.example`
- `.gitignore`
- `requirements.txt`
- `pyproject.toml`
- `vcb_alt/__init__.py`
- `vcb_alt/__main__.py`
- `vcb_alt/cli.py`
- `vcb_alt/config.py`
- `vcb_alt/db.py`
- `vcb_alt/errors.py`
- `vcb_alt/logging_utils.py`
- `vcb_alt/models.py`
- `vcb_alt/scoring.py`
- `vcb_alt/sample_data.py`
- `vcb_alt/security.py`
- `vcb_alt/validation.py`
- `tests/test_cli.py`
- `tests/test_db.py`
- `tests/test_scoring.py`
- `tests/test_validation.py`

## 7. Files To Delete

- None.

## 8. DB Changes

Create SQLite tables:

- `watchlist`
- `evaluations`
- `operation_logs`
- `failed_jobs`

The schema is intentionally smaller than the long-term architecture but compatible with the MVP user flow.

## 9. API Changes

No public HTTP API will be added. Internal command responses use a consistent envelope:

- `ok`
- `status_code`
- `message`
- `data`
- `error`

## 10. UI Changes

CLI UX will include:

- Clear first-run guidance.
- Empty watchlist state.
- Success/error messages.
- JSON output option.
- Duplicate-submit safety for destructive delete via confirmation token.

## 11. Security Changes

- No hardcoded secrets.
- `.env.example` with external API disabled by default.
- Secret redaction in logs.
- Destructive command confirmation.
- No auto-trading.
- No public network listener.

## 12. Test Plan

- Validation unit tests for ticker and numeric constraints.
- Scoring unit tests for deterministic sample inputs.
- DB tests for initialization, watchlist, logs, failed jobs, and data deletion.
- CLI tests for core flow and error behavior.
- Bytecode compile/build check.

## 13. Deployment Prep Plan

- Document local-only private beta deployment.
- Keep external integrations disabled until explicitly configured.
- Provide runbook for backup, restore, logs, and failures.

## 14. Risks And Mitigations

- Risk: The original docs imply richer functionality than MVP. Mitigation: document MVP boundaries and avoid fake live-data claims.
- Risk: Stock decision-support can be mistaken for trading instructions. Mitigation: include disclaimers and keep manual final decision.
- Risk: External APIs can cost money or leak data. Mitigation: disable by default and log only redacted config state.
- Risk: Encoding-damaged docs confuse users. Mitigation: create clean operational docs and leave originals as historical specs.

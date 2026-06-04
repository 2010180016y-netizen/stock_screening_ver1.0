# Changelog

## 1.3.14-hosted-1000-load-recheck - 2026-06-04

### Changed

- Enhanced `tools/host_queue_load_test.py` with worker-protection preflight, auth register/login/delete preflight, provider-failure coverage reporting, and a clearer fail-closed report when the local runner cannot access a usable worker secret.
- Fixed `tools/provider_resilience_test.py` to match the current Yahoo fetch wrapper signature so the deterministic provider outage/budget fixture runs again.
- Recorded the 2026-06-04 hosted Vercel preflight result in `QA_REPORT.md` and `RELEASE_DECISION.md`.

### Verified

- Hosted Vercel preflight wrote `data/hosted_scan_heavy_1000_20260604.json`: `7` requests, `6` successful `2xx`, `1` expected worker-protection `401`, p50 `398.76ms`, p95 `649.85ms`, p99 `649.85ms`.
- Worker endpoint protection was confirmed, auth register/login/delete cleanup passed, and provider budget guard blocked provider-heavy worker execution because the local runner could not obtain a usable worker secret.
- Provider outage/budget simulation passed, targeted SaaS/provider tests passed `26`, full unit suite passed `76`, lint/typecheck/compile smoke passed, and `git diff --check` passed with only Windows LF-to-CRLF warnings.
- Current decision remains `NOT_READY_FOR_1000_USER_SAAS`; the 1000-user worker-completion phase did not execute.

## 1.3.13-legal-copy-decision-support-boundary - 2026-06-04

### Changed

- Replaced investment-action wording in UI/API labels with decision-support, research candidate, monitoring candidate, positive factor, risk marker, and research size reference wording.
- Replaced legacy action-oriented status output with `RESEARCH_CANDIDATE`; secondary eligible output now uses `MONITOR`.
- Renamed the legacy provider-health recommendation policy key to `final_candidate_policy`.
- Reworded Terms, Privacy, and Risk Disclosure as owner/operator-trial drafts that are not legal-reviewed and not usable for public, paid, or unrestricted launch until counsel approval.
- Reworded README, product requirements, operations, release, monitoring, algorithm, and legacy spec docs to avoid action-instruction and promised-outcome language.
- Bumped market-universe cache version to avoid serving stale cached scan reports with old action-oriented labels.

### Verified

- Local checks passed: targeted scoring/portfolio/web/provider-resilience tests `24`, full unit suite `76`, lint `44` files, compile smoke, `git diff --check`, and active legal-copy wording search.

## 1.3.12-explanation-summary-labels - 2026-06-04

### Changed

- Clarified that deterministic scoring and portfolio constraints select research candidates; OpenAI/template providers only generate explanation summaries.
- Added `provider_label`, `role`, `selection_source`, and `selection_method` metadata to ticker analysis summary responses while preserving the existing `ai_summary` compatibility key.
- Updated legacy summary-panel wording to `Explanation summary` / `설명 요약`.
- Updated provider labels so disabled OpenAI/default mode displays as `template summary` and OpenAI mode displays as `OpenAI explanation summary`.
- Updated README, product requirements, implementation plan, operations, legal handoff, operator guide, algorithm review, QA notes, and served JS check artifacts to remove wording that made model/template text look like the selection engine.

### Verified

- Local checks passed: targeted web/provider tests `17`, full unit suite `76`, lint `44` files, compile smoke, and `git diff --check`.
- Wording search found no remaining standalone legacy model-summary labels; remaining `OpenAI` matches are provider names or explanation-summary configuration.

## 1.3.11-saas-legacy-api-migration-gate - 2026-06-03

### Changed

- SaaS mode now returns `410 LEGACY_ENDPOINT_GONE` for legacy global `/api/watchlist`, `/api/scan`, and `/api/select` paths when `user_auth_enabled=true`.
- The legacy response includes a migration message pointing clients to tenant-scoped `/api/user/watchlist`, `/api/user/scan`, or `/api/user/select`.
- Added UI regression coverage proving the served dashboard uses the tenant-aware endpoint helper instead of direct legacy global calls.

### Verified

- Local checks passed: web tests `12`, full unit suite `76`, lint `44` files, compile smoke, and `git diff --check`.

## 1.3.10-market-discovery-watchlist-boundary - 2026-06-03

### Changed

- Disabled automatic starter watchlist seeding for `market_universe` and production SaaS flows.
- Reframed starter tickers as an explicit optional onboarding helper that only fills the manual research drawer.
- Converted the manual ticker input into a secondary collapsible research drawer so the first-screen primary action remains market-wide scan/latest candidates.
- Extended watchlist API metadata with result-boundary and starter-helper fields so clients do not confuse watchlist contents with market-wide research candidate output.

### Verified

- Local checks passed: web tests `10`, full unit suite `74`, lint `44` files, compile smoke, and `git diff --check`.
- Browser smoke was not run because starting the local server was blocked by the current approval/usage limit; static responsive assertions verify mobile ordering keeps `.decision-area` before `.sidebar`.

## 1.3.9-live-data-required-fail-closed - 2026-06-03

### Changed

- Added production live-data validation for market-universe scan reports so `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true` only allows Alpaca snapshot-backed results.
- Blocked sample universe fallback before candidate evaluation when live market data is required.
- Added `live_required` to the scan-report cache key and invalidated fresh cache entries that are not backed by Alpaca snapshots.
- Stopped fresh durable market scan snapshots from being served when they contain sample/demo fallback data under live-data-required mode.

### Added

- Added regression coverage for fail-closed sample fallback, stale sample scan-report cache invalidation, valid cached Alpaca snapshot scans, and durable sample snapshot rejection.

### Verified

- Local checks passed: market-universe tests `6`, SaaS auth/queue tests `21`, full unit suite `72`, lint `44` files, compile smoke, and `git diff --check`.

## 1.3.8-readiness-wording-audit - 2026-06-03

### Changed

- Replaced remaining active public-beta/public-launch wording with owner/operator-trial, external-release blocker, or historical gate wording.
- Renamed public-beta/public-launch criteria headings in release, implementation, SaaS, security, operations, legal, and UX planning docs where they could be mistaken for current approval.
- Removed the stale served-JavaScript external-beta display mapping so the UI does not preserve an obsolete readiness state.

### Verified

- `rg` found no remaining active matches for the requested public-beta, launch-ready, and 1000-user overstatement phrase set.
- A separate unrestricted-release wording search returned no matches for the old phrasing; the current status remains represented through `owner/operator trial`, `public_launch_ready=false`, and `NOT_READY_FOR_1000_USER_SAAS`.

## 1.3.7-market-wide-discovery-ui - 2026-06-03

### Changed

- Reoriented the web dashboard around market-wide discovery instead of manual watchlist scoring.
- Moved the primary first-screen action to "Scan full market / latest candidates" and demoted manual ticker input to an optional research panel.
- Added first-screen scan freshness, provider source, data coverage, and fail-closed state cards so users can understand data posture before reading candidates.
- Updated Korean mode so UI labels, dynamic provider/status values, empty states, and candidate rationale copy are Korean except ticker/company/data identifiers.
- Changed mobile layout order so latest candidate results appear before the optional manual research panel.

### Added

- Added watchlist API metadata that marks manual watchlists as optional research when market-wide discovery is the active product mode.
- Added regression tests for market-wide discovery UI regions, Korean served-JS translations, secondary watchlist metadata, and mobile result-before-watchlist ordering.
- Added secret-safe stderr traceback logging for unexpected HTTP route errors.

### Verified

- Local checks passed: lint `44` files, served dashboard/detail JavaScript syntax checks, compile smoke, and full unit suite `69` tests.
- Browser smoke passed against a local sample market-universe server: English first screen, Korean translation, scan CTA, selected candidates, rationale, provider/data coverage labels, desktop `1280x800`, mobile `390x820`, and no horizontal overflow.
- Browser smoke initially exposed a sandbox-only cache write permission issue when using the workspace data directory; the app path itself was verified with a temp smoke data directory and `/api/scan` returned `7` scanned names with `3` selected research candidates.

## 1.3.6-ops-restore-legal-runbooks - 2026-06-03

### Added

- Rewrote `NEON_BACKUP_RESTORE_DRILL.md` as an executable staging restore runbook with migration drift checks, sample tenant integrity checks, RTO/RPO measurement, rollback procedure, and pass/fail criteria.
- Rewrote `MONITORING_ALERTING_PLAN.md` as an incident runbook covering provider outage, worker failure, queue backlog, Neon/DB errors, auth abuse, and rate-limit saturation.
- Reframed `LEGAL_REVIEW_PACKET.md` as a counsel handoff and marked public, paid, and investment-advice-adjacent launch as blocked until written counsel approval.
- Updated Terms, Privacy, and Risk Disclosure drafts to owner/operator-trial status and removed stale trial-status and research-output wording.

### Changed

- Updated `tools/ops_health_report.py` to read release-status `configured_data` so PostgreSQL, queue, worker, auth, and durable rate-limit posture are not reported as `null`.
- Added operations entry points in `OPERATIONS.md` for provider, worker, queue, DB, auth-abuse, and rate-limit incidents.
- Added hosted scan-heavy load-test evidence and current NOT_READY_FOR_1000_USER_SAAS judgment to QA/release documentation.

### Verified

- Redacted hosted operations health check returned `overall_status=ok`, `release_channel=operator_trial`, and provider warning that Alpaca still needs live diagnostics before production scans.
- Neon restore drill remains pending operator-side staging branch execution; it is now documented as a required launch gate.

## 1.3.5-provider-resilience-guards - 2026-06-03

### Added

- Added a shared provider resilience layer for Alpaca, Finnhub, Yahoo, SEC, OpenAI, and the deterministic template summary provider.
- Added provider timeout, retry, quota budget, circuit breaker, fallback-policy, and secret-safe health reporting configuration.
- Added `/api/provider-health` for operator-safe provider policy/state checks.
- Added durable `provider_alert_events` storage and `/api/admin/provider-alerts` for owner/admin provider incident review.
- Added fixtures for Alpaca `401`, Alpaca `429`, Alpaca timeout, Alpaca malformed JSON, Finnhub quota exhaustion, Yahoo outage, and OpenAI timeout/template fallback.

### Changed

- Routed Alpaca snapshots/assets, Finnhub enrichment, SEC filings, Yahoo chart fetches, and OpenAI summaries through the common provider policy layer.
- Production live-data-required scans remain fail-closed: provider failures prevent final candidate output instead of falling back to sample/demo output.
- Worker scan failures now create provider alert events when a provider-originated failure is detected.
- Provider status now links to provider health and provider alert endpoints.

### Verified

- `git diff --check` passed with no whitespace/conflict errors.
- Targeted provider/web/SaaS tests passed: `32` tests.
- Full local verification passed: lint `44` files, typecheck `415` objects, unittest `68` tests, and compile/build smoke.

## 1.3.4-worker-owned-market-snapshots - 2026-06-03

### Added

- Added durable `market_scan_snapshots` storage for market-universe scan reports, selected candidates, provider metadata, freshness, failures, retry state, and dead-letter state.
- Added worker-owned market snapshot processing before tenant watchlist jobs.
- Added `/api/jobs/market-scan/{id}` for global market snapshot job status.
- Added admin queue-status visibility for market snapshot counts and latest job state.
- Added regression tests for snapshot enqueue/idempotency, worker refresh, fresh reads, retry scheduling, and dead-letter recovery.

### Changed

- In production SaaS market-universe mode, `/api/user/scan` now returns a fresh durable snapshot or a `202` queued/pending job status instead of directly executing provider-heavy scans.
- `/api/jobs/scan` now uses the same durable market snapshot path in `market_universe` mode.
- SaaS readiness copy now reflects worker-owned market snapshots and the need to rerun hosted provider load tests after Alpaca is fixed.

### Verified

- Targeted SaaS/DB/web tests passed.
- Full unit test suite, lint, typecheck, and compile/build smoke passed locally.
- Production deploy completed; `POST /api/user/scan` returned `202` with a queued market snapshot job instead of executing a direct provider-heavy scan.
- Production market-scan job status and admin queue-status visibility were verified.
- Protected worker trigger correctly rejected the local verification attempt without `VCB_ALT_WORKER_TOKEN`.

## 1.3.3-owner-trial-readiness-copy - 2026-06-03

### Changed

- Replaced active external-release readiness wording across README, deployment, operations, release, QA, and web UI copy with owner/operator-trial wording.
- Reframed prior 1000-user and queue-load successes as historical evidence, not current public-launch approval.
- Updated current public-readiness wording to require `public_launch_ready=false`, `NOT_READY_FOR_1000_USER_SAAS`, Alpaca diagnostics `ready=true`, and live market-universe scan verification before any external release claim.

### Verified

- Ran `rg` for stale external-release readiness wording; only explicit not-ready status values remained.

## 1.3.2-alpaca-credential-diagnostics - 2026-06-03

### Added

- Added secret-safe Alpaca diagnostics at `/api/provider-diagnostics/alpaca`.
- Added Alpaca diagnostic coverage for Paper Trading, Live Trading, and Market Data snapshot endpoint acceptance.
- Added regression tests proving diagnostics classify invalid credentials without returning key or secret values.

### Changed

- Provider status now points operators to the Alpaca diagnostics endpoint when Alpaca credentials are configured but not live-verified.
- Provider key setup docs now require `/api/provider-diagnostics/alpaca` after Vercel env changes.
- Release and QA docs now state that production remains blocked while Alpaca returns HTTP 401.

### Verified

- Targeted diagnostics/web tests passed.
- Full unit test suite, lint, typecheck, and compile/build smoke passed locally.
- Production deploy completed and `/api/provider-diagnostics/alpaca` returned `key_context_mismatch_or_invalid` with Alpaca HTTP `401` for Paper Trading, Live Trading, and Market Data snapshot checks.
- Production `/api/user/scan` was re-tested and failed closed with Alpaca HTTP `401`, returning no sample fallback candidates.

## 1.3.1-operability-review - 2026-06-03

### Added

- Added `OPERABILITY_REVIEW.md` with the current production readiness decision, live API verification findings, public-launch blockers, removal candidates, prioritized improvement list, and copy-ready follow-up implementation prompts.

### Verified

- Production `/api/config`, `/api/provider-status`, `/api/release-status`, and `/api/saas-readiness` were checked against `https://stockscreeningver10.vercel.app`.
- Production authenticated `/api/user/scan` was checked and failed closed with Alpaca market-universe `HTTP 401`, confirming the live all-market scan path is still not operable for unrestricted external release.

## 1.3.0-market-universe-discovery - 2026-05-26

### Added

- Added `VCB_ALT_SCAN_MODE=market_universe` as the product scan mode for market-wide discovery instead of user-entered watchlist-only evaluation.
- Added `vcb_alt.market_universe` for Alpaca active-asset universe loading, Alpaca multi-symbol snapshot prefiltering, candidate normalization, Finnhub/CSV enrichment, and portfolio selection.
- Added short-TTL market scan report caching so many users can reuse the same fresh discovery result instead of triggering provider calls per click.
- Added Alpaca assets endpoint fallback across paper and live trading hosts so market-universe loading works with either key type when credentials are valid.
- Added market-universe configuration for provider, max symbols, prefilter size, snapshot batch size, and fail-closed live-data enforcement.
- Added `data/universe.example.csv` and regression coverage for sample fallback plus cached Alpaca snapshot prefiltering.

### Changed

- Web, CLI, and queue-worker scan paths now use market-universe discovery when configured.
- `G_TECHNICAL_MOMENTUM` now includes Alpaca intraday surge and relative-volume momentum, while stale data remains blocked.
- Algorithm documentation now states that OpenAI is explanation-only; stock selection is deterministic scoring over provider data.

## 1.2.4-algorithm-review-and-ko-localization - 2026-05-24

### Added

- Added `ALGORITHM_REVIEW.md` with an end-to-end explanation of data inputs, archetype scoring, data coverage gating, and final portfolio selection.
- Added regression coverage proving equal-score portfolio candidates prefer higher data coverage.

### Changed

- Final selection tie-breaks now prefer higher `data_coverage_score` before volatility and sizing tie-breaks.
- Korean UI mode now translates dynamic dashboard/detail strings, including archetype labels, public review labels, rationale bullets, precision notes, warnings, data coverage labels, explanation summary sections, and expert consensus copy.
- English UI mode remains unchanged; ticker symbols and company/security names remain untranslated.

### Verified

- Local lint passed: `lint ok (40 files)`.
- Local typecheck passed: `type hints ok (308 objects)`.
- Full unit test suite passed: `56` tests.
- Served dashboard/detail JavaScript passed `node --check`.
- Compile/build passed.

## 1.2.3-saas-scan-button-fix - 2026-05-24

### Fixed

- Fixed the public SaaS dashboard scan button by routing authenticated users to tenant-scoped `/api/user/scan` and `/api/user/select` instead of the legacy global `/api/scan` and `/api/select` endpoints that are blocked in SaaS mode.
- Added automatic browser-scoped tenant session recovery so stale local demo credentials no longer leave the dashboard unable to scan.
- Historical legacy note: automatic starter watchlist seeding was added for new browser tenants in the earlier watchlist-centered flow; current market-wide discovery uses only an optional starter research helper.

### Changed

- `/api/user/scan` now returns the evaluated watchlist and final selection in one response, reducing the user-facing scan flow from two round trips to one when the user clicks `Run scan`.
- Tenant scan persistence batches evaluation writes into one commit per watchlist scan instead of committing per ticker.
- Added code comments around the synchronous tenant scan path and batched persistence optimization.

### Verified

- Local lint passed: `lint ok (40 files)`.
- Local typecheck passed: `type hints ok (307 objects)`.
- Full unit test suite passed: `55` tests.
- Served dashboard/detail JavaScript passed `node --check`.
- Local SaaS API smoke passed: registered a tenant user, added `7` tickers, scanned `7`, and selected `3`.
- Production deploy `dpl_EJwfpEvi9SnziMreYcbGAMeyVKGR` is live at `https://stockscreeningver10.vercel.app`.
- Production SaaS API smoke passed: scanned `7` tickers in `69ms` and selected `PLTR`, `VST`, `MSTR`.
- In-app browser verification passed: clicking `Run scan` showed `Scan completed in 21 ms` and rendered candidate results.
- Hosted health smoke passed after deploy: `100/100` HTTP `200`, `0` errors, p95 `955.29ms`.

## 1.2.2-public-launch-gate-tooling - 2026-05-22

### Added

- Added `tools/host_queue_load_test.py` for hosted auth/watchlist/queue/job-polling load smoke.
- Added `tools/provider_resilience_test.py` for deterministic provider outage and budget-exhaustion simulation.
- Added `tools/ops_health_report.py` for redacted health/release/provider/readiness monitoring and optional webhook alerting.
- Added `AUTH_MFA_RBAC_PLAN.md`, `MONITORING_ALERTING_PLAN.md`, `NEON_BACKUP_RESTORE_DRILL.md`, and `LEGAL_REVIEW_PACKET.md`.
- Added `require_role(user, allowed_roles)` as the code-level RBAC helper for future admin/export/delete actions.
- Added per-user export and account deletion APIs for SaaS privacy operations.
- Added tenant admin users, audit events, and queue-status APIs for operator visibility.
- Added audit event storage for sensitive user actions.
- Added stale running scan-job recovery before worker processing.
- Added `tools/queue_load_test.py` for local queue-backed 1000-user scan simulation.

### Changed

- Updated load-test and README documentation for the new public-launch gate tooling.
- Serialized PostgreSQL SaaS schema initialization with an advisory transaction lock to prevent serverless cold-start DDL races.
- Split the Vercel `/api/health` runtime path so health checks do not execute database DDL during traffic spikes.
- Restored corrupted Korean dashboard/detail-page translation strings and verified embedded JavaScript syntax.

### Verified

- Local queue-backed 1000-user load simulation passed: `1000` jobs completed, `30000` tenant evaluations, `0` failures.
- Regression verification after the serverless DDL-race fix passed: lint, typecheck, and `53` unit tests.
- Production redeploy `dpl_AkT17aQUWBzrMZy7dugaGuMyRDfR` passed hosted health smoke: `1000/1000` HTTP `200`, `0` errors, p95 `1668.44ms`.
- Production queue-enqueue smoke passed for `3` users and `3` queued scan jobs with `0` errors.
- Dashboard and detail JavaScript passed `node --check`; final regression verification passed lint, typecheck, and `53` tests.
- Final production deploy `dpl_7iWJ3a9cK3WDWCKwuy43SztLb5Vd` passed hosted health smoke: `200/200` HTTP `200`, `0` errors, p95 `1313.67ms`.
- Worker-triggered hosted queue completion smoke passed for `10/10` jobs after rotating the production worker token.
- Single-runner `50` user hosted completion attempt completed `24` jobs and then hit the production durable rate limiter, confirming the next 1000-user test needs distributed load generation or a dedicated staging rate-limit profile.
- Added endpoint-specific durable rate-limit buckets for auth/signup, authenticated tenant APIs, worker calls, and default public API traffic.
- Hosted worker-triggered 1000-user completion test passed: `1000` queued jobs, `1000` completed jobs, `0` errors, p95 `6049.49ms`.
- Post-1000-test production health smoke passed: `300/300` HTTP `200`, `0` errors, p95 `1572.27ms`.

## 1.2.1-expert-read-speed-accuracy - 2026-05-22

### Fixed

- Fixed PostgreSQL session authentication when psycopg returns `TIMESTAMPTZ` as `datetime`.
- Made PostgreSQL scan-job claiming atomic with `FOR UPDATE SKIP LOCKED`.
- Added PostgreSQL advisory locking to the durable database rate limiter.
- Made operation/export JSON decoding tolerant of PostgreSQL JSON and datetime objects.

### Changed

- Queued tenant scans now persist each ticker result into `tenant_evaluations` for user history and operator audit.
- Yahoo/Stooq process-level market-data caches now refresh on a TTL bucket so long-running workers cannot serve stale data beyond the configured cache window.
- Updated README, implementation plan, SaaS plan, load-test plan, release decision, and readiness text to reflect Neon cutover and the remaining true blockers.

### Verified

- Targeted auth, SaaS queue, DB, and provider cache regression tests passed.
- Full local verification passed: lint, typecheck, `50` tests, compile/build, benchmark, CLI smoke, and local web API smoke.

## 1.2.0-neon-postgres-saas-cutover - 2026-05-22

### Added

- Connected Neon PostgreSQL to the Vercel project.
- Enabled production SaaS mode with PostgreSQL, per-user auth, database rate limits, scan queue, worker token, and worker cron flags.
- Added `psycopg[binary]` as the production PostgreSQL runtime dependency.

### Verified

- Production release status now reports `production_saas_ready=true`.
- Production SaaS smoke passed: user registration, tenant watchlist, scan job queue, protected worker processing, and job result lookup.
- Hosted health load test passed after PostgreSQL cutover: `1000/1000` requests returned `200`, `0` errors, p95 `1917.36ms`.

## 1.1.1-vercel-worker-loadtest - 2026-05-22

### Added

- Added protected `/api/admin/run-worker` endpoint for Vercel Cron or manual worker triggering.
- Added `VCB_ALT_WORKER_TOKEN` and `VCB_ALT_WORKER_CRON_ENABLED`.
- Added Vercel Cron route using a Hobby-compatible daily schedule.
- Added tests covering worker endpoint authentication and processing.

### Changed

- Cleared stale Vercel deployments stuck in `Initializing` and `Queued`.
- Deployed the latest safe owner-trial build to `https://stockscreeningver10.vercel.app`.

### Verified

- Hosted health load test passed: `1000/1000` requests returned `200`, `0` errors, p95 `2120.62ms`.
- Final local verification passed: lint, typecheck, `44` tests, and compileall.

## 1.1.0-saas-readiness - 2026-05-21

### Added

- Added optional PostgreSQL runtime adapter and PostgreSQL migration coverage for tenant users, sessions, tenant watchlists, rate-limit events, and scan jobs.
- Added `VCB_ALT_PRODUCTION_SAAS_MODE` guard so public SaaS mode refuses to boot unless PostgreSQL, per-user auth, database rate limiting, and scan queue are all enabled.
- Added database-backed rate limiting for multi-process/serverless deployments.
- Added durable scan job enqueue/list/detail APIs and a `worker run-once` command for queue-backed user watchlist scans.
- Added hosted load-test tooling in `tools/host_load_test.py`.

### Changed

- When per-user auth is enabled, legacy global watchlist/scan/select APIs are blocked in favor of tenant-scoped APIs.
- Updated SaaS readiness reporting to reflect the new production guards, queue, and durable rate-limit layer.

### Verified

- Local 1000-user / 30,000-evaluation simulation passed with `0` errors and tenant isolation passed.
- Hosted load-test execution was prepared but not run because the escalation request was rejected by the current usage limit.

## 1.0.1-operator-trial - 2026-05-21

### Changed

- Optimized `/api/ticker-analysis` so profile rendering reuses the already-enriched snapshot instead of calling market/research providers a second time.
- Cached Vercel serverless bootstrap config after warm-process initialization to reduce repeated setup overhead.
- Added `Secure` to the shared-token cookie when requests are forwarded over HTTPS.
- Updated owner-trial docs to use verified Finnhub enrichment and leave Alpaca disabled until the credential pair is fixed.

### Added

- Added tests for HTTPS secure cookie behavior and snapshot reuse-compatible profile loading.

## 1.0.0-operator-trial - 2026-05-20

### Added

- Added `/api/release-status` so the deployed app can report whether it is an owner/operator-trial build or external-release build.
- Added `OPERATOR_TRIAL_GUIDE.md` with the owner usage URL, workflow checklist, provider mode, and public-launch blockers.
- Added `PROVIDER_KEYS_SETUP.md` with safe Vercel/local instructions for Alpaca, Finnhub, SEC, and OpenAI provider keys.

### Changed

- Marked the current deployed scope as an operator pre-user usage build: usable by the owner, not ready for unrestricted public SaaS.

## 0.9.0 - 2026-05-20

### Added

- Added optional Alpaca intraday snapshot overlay with latest quote/trade/minute-bar cache fields.
- Added SEC submissions metadata enrichment for latest filing type, date, URL, and recent filing catalyst flag.
- Added Finnhub analyst rating trend parsing for broker-rating counts and revision score.
- Added deterministic explanation summaries with optional OpenAI Responses API mode and local cache fallback.
- Added ticker detail explanation summary panel plus intraday, short-interest, option put/call, and analyst-score metrics.
- Added cache-fixture tests for Alpaca, Finnhub analyst data, SEC filings, and explanation summary output.

### Changed

- Bumped scoring version to `mvp-market-v0.5.0`.
- Data coverage now recognizes earnings surprise, analyst trends, news count, SEC filing catalysts, and analyst positioning context.

## 0.8.0 - 2026-05-20

### Added

- Added a research-data provider layer separate from the market-data provider.
- Added `VCB_ALT_RESEARCH_DATA_PROVIDER`, `VCB_ALT_FINNHUB_API_KEY`, and `VCB_ALT_RESEARCH_DATA_CACHE_TTL_HOURS`.
- Added optional Finnhub enrichment for fundamentals, earnings surprise, recent news catalysts, insider transactions, short interest, and option-chain open interest.
- Added `finnhub_csv` mode so operator CSV enrichment can override or fill gaps after API enrichment.
- Added option-chain fields: `call_open_interest`, `put_open_interest`, and `put_call_ratio`.
- Added tests using local Finnhub cache fixtures so enrichment can be verified without live network calls or credentials.

### Changed

- Provider status now reports configured research provider capabilities without exposing API keys.
- Data coverage can now be satisfied by API-backed research enrichment instead of only `data/enrichment.csv`.

## 0.7.0 - 2026-05-20

### Added

- Added `data/enrichment.csv` support for applying operator-verified fundamentals, catalysts, short/options, insider, float, and related context over Yahoo/Stooq market snapshots.
- Added `data/enrichment.example.csv` as the enrichment template.
- Added data coverage scoring across market, fundamental, catalyst, and positioning groups.
- Added evaluation output fields for data coverage score, label, and detail.
- Added tests proving price-only market data is blocked from final selection and enriched Yahoo data can pass.

### Changed

- Bumped scoring version to `mvp-market-v0.4.0`.
- Blocked chart-only price/volume scans from final selection until data coverage reaches `60/100`.
- Updated provider status warnings to report when enrichment is missing.

## 0.6.2 - 2026-05-19

### Added

- Added persisted Korean/English language toggles to the dashboard and ticker detail page.
- Added mobile table-card rendering so scan results remain inside the viewport on narrow screens.
- Added code comments documenting the responsive overflow guard.

### Changed

- Added responsive layout safeguards for dashboard cards, tables, metric boxes, buttons, and ticker detail panels.
- Replaced the basic Arial stack with a clean app-standard system font stack including Inter, Segoe UI, Roboto, Noto Sans KR, and Apple SD Gothic Neo.

## 0.6.1 - 2026-05-19

### Added

- Added ticker detail pages at `/ticker/<ticker>` with five-year price/volume chart, sector, industry, current status, selection rationale, and expert-consensus review sections.
- Added `/api/ticker-analysis?ticker=<ticker>` for detail-page data.
- Added five-year chart history payloads with honest real-time/freshness labeling.
- Added curated sector/industry fallback profiles for the default watchlist.
- Added tests for ticker analysis API, chart history, profile/industry data, and selection rationale.

### Changed

- Candidate card and table clicks now navigate to the ticker analysis page instead of only opening a modal.
- Updated planning and UX documents with the expert consensus for what a stock status-analysis page must contain.

## 0.6.0 - 2026-05-19

### Added

- Added local per-user SaaS auth primitives with PBKDF2 password hashing, opaque session tokens, and bearer-session authentication.
- Added tenant/user/session/tenant-watchlist tables for SaaS-boundary testing.
- Added tenant-scoped user watchlist APIs: `/api/auth/register`, `/api/auth/login`, `/api/me`, and `/api/user/watchlist`.
- Added basic in-process API rate limiting for the current stdlib server.
- Added PostgreSQL target migration at `migrations/postgres/001_saas_core.sql`.
- Added `tools/load_test.py` and executed a 1000-user / 30,000-evaluation local load simulation.
- Added auth, session, tenant-isolation, and rate-limit tests.

### Changed

- Updated SaaS readiness status to reflect partial progress on auth, tenant isolation, database migration, API hardening, and load testing.
- Extended `.env.example` with disabled-by-default user auth and rate-limit settings.

## 0.5.4 - 2026-05-19

### Added

- Added external-review safety layer with SaaS-safe `public_label` values on evaluation results.
- Added `/api/provider-status` to expose provider capabilities, cache TTL, timeout, and warnings without secrets.
- Added starter `TERMS.md`, `PRIVACY.md`, and `RISK_DISCLOSURE.md`.
- Added dashboard links for Risk Disclosure, Privacy, and Terms.
- Added tests for public labels and provider-status behavior.

### Changed

- Updated dashboard copy from direct trade-action wording to neutral review wording while preserving internal audit status fields.
- Updated implementation and SaaS plans to reflect the deployed decision-first UI and external-review safety gate.

## 0.5.3 - 2026-05-19

### Added

- Added `UX_RESEARCH_FINDINGS.md` summarizing external stock-screener user pain points and how they map to this product.
- Added decision-first dashboard regions for final candidates, actionable setups, monitor/excluded names, data status, and score detail review.
- Added dashboard tests that assert the key decision-first UI regions are present.

### Changed

- Reworked the web dashboard UI in `vcb_alt/web.py` to keep the supplied dark operations-desk direction while using real API data instead of hardcoded scores or tickers.
- Preserved the no-frontend-build, no-CDN architecture by implementing the redesign with native HTML, CSS, and JavaScript.

## 0.5.2 - 2026-05-18

### Added

- Added Vercel serverless entrypoint at `api/index.py` and root rewrite config in `vercel.json`.
- Added `VCB_ALT_DATA_DIR` and `VCB_ALT_LOG_DIR` environment variables so serverless deployments can write ephemeral cache/log data under `/tmp`.
- Added Cloudflare Worker/D1 deployment source under `deploy/cloudflare-worker.js` as an alternate edge deployment path.
- Added `.vercelignore` to keep local data, logs, test files, screenshots, and alternate deployment files out of Vercel uploads.

### Changed

- Updated public deployment documentation with Vercel runtime environment-variable deployment guidance and explicit ephemeral-storage warnings.
- Deployed and verified the Vercel production alias `https://stockscreeningver10.vercel.app` as a token-protected private-beta service.

### Notes

- Cloudflare Worker deployment was prepared, but Cloudflare API deployment is blocked until the account email address is verified.

## 0.5.1 - 2026-05-17

### Added

- Added `research.md` with a detailed system research report covering CLI, web, DB, providers, scoring, portfolio selection, security, operations, tests, and current scaling limits.
- Added `plan.md` with Feature 00 implementation details for input-based/keyset paging across watchlist, logs, and failures.

### Changed

- Updated README to point operators and maintainers to the new research, planning, QA, and release-decision documents.
- Added API contract notes that offset paging is intentionally not the planned list-pagination strategy.

## 0.5.0 - 2026-05-17

### Added

- Added `yahoo` automatic chart provider and optional `stooq` CSV provider with local cache and network timeout.
- Added price/volume-derived precision metrics: 12-week/12-month return, 52-week drawdown, moving-average distances, trend template score, surge score, relative strength versus SPY, and risk/reward ratio.
- Added public web mode guarded by `VCB_ALT_WEB_ACCESS_TOKEN`.
- Added `.env.example`, `Dockerfile`, `.dockerignore`, `render.yaml`, and `PUBLIC_DEPLOYMENT.md` for token-protected web deployment.
- Added Yahoo/Stooq provider tests and public web token-guard tests.

### Changed

- Historical legacy note: the web server seeded the sample watchlist on first run when `VCB_ALT_AUTO_SEED_SAMPLE=true`; current market-wide discovery and production SaaS flows ignore this auto-seed path.
- Scoring now incorporates market-derived trend and surge bonuses while preserving the existing archetype model.
- Documentation now distinguishes local/private use, token-protected public demo use, and true 1000-user SaaS requirements.

## 0.4.0 - 2026-05-17

### Added

- Added local web dashboard served by `python -m vcb_alt web --host 127.0.0.1 --port 8765`.
- Added dashboard APIs for health, config, watchlist, scan, final selection, logs, failures, and SaaS readiness.
- Added automatic dashboard first-load scan and final candidate selection.
- Added local throughput benchmark command: `python -m vcb_alt benchmark --repeat 1000`.
- Added web/API tests and benchmark test coverage.

### Changed

- The user-facing first screen now shows actual work state instead of a static/empty landing page.
- Web dashboard remains local-only and bound to localhost by default.

## 0.3.0 - 2026-05-16

### Added

- Added manual CSV data provider using `data/snapshots.csv`.
- Added `data/snapshots.example.csv` template for operator-supplied current snapshots.
- Added portfolio candidate selection with `python -m vcb_alt select`.
- Added selection constraints: max positions, total suggested exposure cap, duplicate primary archetype avoidance, and high-volatility archetype limit.
- Added provider and portfolio tests.

### Changed

- Default selection exposure cap is 75% so the intended 3-position concentrated portfolio can be produced while still staying below full exposure.
- Scan/evaluate output now carries `data_as_of` from the selected provider.

## 0.2.0 - 2026-05-16

### Added

- Added 1000-user SaaS target architecture documentation.
- Added multi-tenant PostgreSQL data model sketch.
- Added API contract, security/compliance plan, operations plan, migration plan, and load test plan.
- Added `python -m vcb_alt saas-readiness` to make public SaaS blockers explicit and testable.
- Added SaaS readiness tests to prevent accidental claims that the current CLI is ready for 1000 users.

### Changed

- Clarified that the current CLI remains local/private-beta only and must not be exposed as a shared service.
- Defined the future approach as domain-logic reuse with new auth/API/PostgreSQL/worker/observability boundaries.

## 0.1.0 - 2026-05-16

### Added

- Created audit and product-redefinition docs: `AUDIT_REPORT.md`, `PRODUCT_REQUIREMENTS.md`, `USER_FLOWS.md`, `RELEASE_CRITERIA.md`, `IMPLEMENTATION_PLAN.md`, `ASSUMPTIONS.md`.
- Added installable Python package skeleton under `vcb_alt/`.
- Added standard-library CLI with `init-db`, `doctor`, `watchlist`, `evaluate`, `scan`, `morning`, `weekly`, `self-test`, and `admin` commands.
- Added SQLite tables for watchlist, evaluations, operation logs, and failed jobs.
- Added deterministic sample/offline stock data provider.
- Added six-archetype MVP scoring and risk warnings.
- Added input validation and friendly error envelopes.
- Added secret redaction for logs and metadata.
- Added local export and destructive delete confirmation.
- Added tests for validation, scoring, DB, and CLI flows.
- Added operational docs: `README.md`, `SETUP.md`, `DEPLOYMENT.md`, `TESTING.md`, `OPERATIONS.md`.

### Changed

- Reframed current release target as local-only private beta instead of public SaaS.
- Disabled external APIs by default to avoid cost, privacy, and legal risks.

### Fixed

- Replaced documentation-only state with a runnable local product baseline.
- Closed the P0 gap where setup instructions referenced non-existent code.
- Ensured SQLite connections close correctly on Windows to prevent locked test DB files.

### Known Limitations At 0.1.0

- Live market data was not implemented in 0.1.0. This was later addressed for EOD price/volume data in 0.5.0.
- Multi-user authentication and web dashboard are out of scope.
- No broker integration or automatic trading.

# QA Report

QA date: 2026-05-18 KST

Latest verification update: 2026-06-10 KST

## Public 1000-User SaaS Blocker Closure Pass - 2026-06-10 KST

Scope:

- Rechecked the codebase against the current blocker list for public 1000-user SaaS launch.
- Hardened production SaaS auth boundaries so query-string access tokens and query-string worker tokens are disabled in production mode.
- Reworked tenant market-universe scan jobs so user-triggered jobs read a fresh durable worker-owned market snapshot or return pending/enqueued state; provider-heavy `scan_market_universe` calls remain worker-owned.
- Added tenant/global provider-alert separation and global-operator visibility.
- Added trusted-proxy-only `X-Forwarded-For` handling and JSON body-size/invalid-JSON guards.
- Extracted dashboard/detail/login/legal HTML, CSS, and served JS into `vcb_alt/web_assets/` and made `web.py` load those UTF-8 files first, with embedded constants retained only as fallback.
- Replaced served dashboard/detail JavaScript Korean i18n output with valid UTF-8 strings and added regression coverage for broken served text.
- Ran local API, served asset, desktop viewport, and mobile viewport smoke checks.

Commands run:

```powershell
python -m unittest tests.test_web tests.test_saas_auth
python -m unittest discover -s tests
python -m tools.lint
python -m tools.typecheck
python -m compileall -q vcb_alt tests tools api
$env:VCB_ALT_SCAN_MODE='market_universe'; $env:VCB_ALT_DATA_PROVIDER='sample'; $env:VCB_ALT_EXTERNAL_API_ENABLED='false'; $env:VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA='false'; $env:VCB_ALT_PUBLIC_WEB_ENABLED='false'; $env:VCB_ALT_DATABASE_URL='sqlite:///./data/local_smoke_8792.db'; python -m vcb_alt web --host 127.0.0.1 --port 8792
Invoke-WebRequest http://127.0.0.1:8792/api/health
Invoke-WebRequest http://127.0.0.1:8792/api/config
Invoke-WebRequest http://127.0.0.1:8792/assets/app.js
Invoke-WebRequest http://127.0.0.1:8792/assets/detail.js
Invoke-WebRequest http://127.0.0.1:8792/
gh --version
```

Results:

- Targeted web/SaaS tests passed: `39` tests.
- Full unit suite passed: `82` tests.
- Lint passed: `lint ok (44 files)`.
- Typecheck passed: `type hints ok (428 objects)`.
- Compile smoke passed for `vcb_alt`, `tests`, `tools`, and `api`.
- Local web smoke passed for `/api/health`, `/api/config`, `/assets/app.js`, `/assets/detail.js`, and `/`.
- Served JS encoding check passed: dashboard/detail assets contained valid Korean strings and no replacement-character mojibake.
- Extracted web asset test passed for `login.html`, `index.html`, `detail.html`, legal pages, `app.css`, `app.js`, and `detail.js`.
- Desktop browser smoke passed at `1280px`: no horizontal overflow, Korean toggle present, primary CTA visible, and primary CTA text translated to `시장 전체 스캔/최신 후보 확인`.
- Mobile browser smoke passed at `390px`: no horizontal overflow, no escaping text boxes detected, Korean toggle worked, and primary CTA stayed visible.
- Local smoke server was stopped after verification.

Hosted load-test gate:

- GitHub Actions hosted load-test workflow could not be dispatched from this workstation because `gh` is not installed.
- The available GitHub connector tools exposed workflow read/rerun helpers but no new manual workflow-dispatch tool for this run.
- This local run therefore does not prove the required hosted gate: worker trigger, queue completion, snapshot read, provider call delta, queue depth, provider failure handling, `db_error_count=0`, and `load_test_passed=true`.
- Required next execution remains the secret-backed CI/operations runner with `VCB_ALT_WORKER_TOKEN` or `CRON_SECRET` available as a protected secret.

Release conclusion:

- Current state remains `public_launch_ready=false`.
- Current release decision remains `NOT_READY_FOR_1000_USER_SAAS`.
- The code path is safer for owner/operator trial, but public 1000-user SaaS launch remains blocked until the hosted worker-completion load-test gate and live-provider production scan evidence pass.

## Hosted Scan-Heavy 1000-User Load Test Recheck - 2026-06-04 KST

Scope:

- Rechecked the deployed Vercel owner/operator-trial environment with a hosted scan-heavy 1000-user load-test runner.
- Updated `tools/host_queue_load_test.py` so the report now records worker-protection preflight, auth register/login/delete preflight, provider-failure coverage status, and a clearer fail-closed reason when the local runner cannot access the worker secret.
- Fixed `tools/provider_resilience_test.py` after the Yahoo fetch wrapper signature changed, so the deterministic provider outage/budget fixture runs again.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load --confirm-provider-budget --expected-provider-calls 280 --max-provider-calls 350 --min-provider-budget-remaining 350 --snapshot-read-sample 1000 --out data\hosted_scan_heavy_1000_20260604.json
C:\stable-diffusion-ui\installer_files\env\python.exe tools\provider_resilience_test.py
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_saas_auth tests.test_provider_resilience
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests tools api
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
```

Hosted result:

- Result file: `data/hosted_scan_heavy_1000_20260604.json`.
- Final decision: `NOT_READY_FOR_1000_USER_SAAS`.
- Load-test pass: `false`.
- Requests executed before safe block: `7`.
- HTTP status counts: `2xx=6`, `4xx=1`, `5xx=0`; the single `401` was the expected unauthenticated worker-protection probe.
- Overall latency: p50 `398.76ms`, p95 `649.85ms`, p99 `649.85ms`, max `649.85ms`.
- Auth preflight: register `201`, login `200`, account delete cleanup `200`.
- Protected worker trigger preflight: unauthenticated `/api/admin/run-worker?limit=1` returned `401`, confirming the endpoint is protected.
- Provider health/budget preflight: Alpaca, Finnhub, Yahoo, and template providers reported ready budgets; OpenAI and SEC were not configured.
- Provider call budget guard: provider calls were not allowed because the local runner could not obtain a usable worker token.
- Registration/login/enqueue load phase: `0/1000` executed because worker-trigger completion could not be authorized.
- Worker trigger/completion: `0` processed, `0` failed, `0` completed.
- Job polling: `0` jobs.
- Snapshot reads: `0` attempted.
- Queue depth: no authenticated admin queue read was executed in the blocked run.
- DB error count: `0`.
- Provider call count delta: not measured because no provider-heavy worker scan was triggered.
- Provider failure handling coverage: provider health and budget were checked, but hosted job failure/dead-letter and admin provider-alert paths were not exercised because the worker/admin context was unavailable.

Secret/access note:

- Vercel production env pull showed worker-related keys exist, but the local runner received `VCB_ALT_WORKER_TOKEN` and `CRON_SECRET` as zero-length values. No secret values were printed or stored.
- Without a usable worker secret, the safe behavior is to block the hosted completion test before creating 1000 tenants or consuming provider budgets.

Local verification:

- Provider outage/budget simulation passed with structured failures: `failure_count=3`, `provider_calls_before_budget_stop=6`, `scan_ok=true`, `select_ok=true`.
- Targeted SaaS/provider tests passed: `26` tests.
- Full unit test suite passed: `76` tests.
- Compile smoke passed for `vcb_alt`, `tests`, `tools`, and `api`.
- Lint passed: `lint ok (44 files)`.
- Typecheck passed: `type hints ok (423 objects)`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.

Conclusion:

- The hosted 1000-user scan-heavy completion test has not passed.
- The product remains `NOT_READY_FOR_1000_USER_SAAS` for public operation.
- Required next gate: run the same command from an environment that can access the production worker secret and prove 1000-user registration/login, scan enqueue, worker trigger, job polling, snapshot read, provider failure handling, cleanup, provider call deltas, queue depth, and DB error metrics with `load_test_passed=true`.

## Legal Copy Decision-Support Boundary - 2026-06-04 KST

Scope:

- Reviewed UI, README, docs, API response labels, and legal draft pages for wording that could be interpreted as investment-action guidance before legal review.
- Replaced action-oriented wording with decision-support, research candidate, monitoring candidate, positive factor, risk marker, and research size reference language.
- Replaced legacy action-oriented API status output with `RESEARCH_CANDIDATE` and the legacy provider-health recommendation policy key with `final_candidate_policy`.
- Updated Terms, Privacy, and Risk Disclosure so they clearly state they are owner/operator-trial drafts, not legal-reviewed launch documents.
- Bumped the market-universe cache version so old cached sample scan reports with obsolete action-oriented labels are not reused.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_scoring tests.test_portfolio tests.test_web tests.test_provider_resilience
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
rg investment-action/legal-copy phrase checks across UI/docs/API labels
```

Result:

- Targeted scoring/portfolio/web/provider regression tests passed: `24` tests.
- Full unit test suite passed: `76` tests.
- Compile smoke passed for `vcb_alt` and `tests`.
- Lint passed: `lint ok (44 files)`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.
- Wording search found no remaining active investment-action phrases in UI/docs/API labels. Remaining broad-search hits are internal provider/schema/test fixture names, PostgreSQL `pg_advisory_xact_lock` technical references, and an ignored generated old `data/market_universe/scan_reports/v1` cache file that is no longer used after the cache-version bump.

## Explanation Summary Label Boundary - 2026-06-04 KST

Scope:

- Reviewed UI, README, docs, API response labels, and served JS check artifacts for wording that could imply a model directly selects stocks.
- Preserved the existing `ai_summary` response key for compatibility, but added explicit `provider_label`, `role`, `selection_source`, and `selection_method` metadata.
- Updated legacy summary-panel wording to `Explanation summary` / `설명 요약`.
- Updated summary provider display so default/OpenAI-disabled mode is labeled `template summary`; OpenAI mode is labeled `OpenAI explanation summary`.
- Updated docs to state that deterministic scoring and portfolio constraints select candidates, while OpenAI/template providers only explain those results.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_web tests.test_provider_resilience
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
rg -n -i "<standalone legacy model-summary wording pattern>" . --glob "*.md" --glob "*.py" --glob "*.js" --glob "*.json" --glob "!node_modules/**" --glob "!.git/**"
```

Result:

- Targeted web/provider regression tests passed: `17` tests.
- Full unit test suite passed: `76` tests.
- Compile smoke passed for `vcb_alt` and `tests`.
- Lint passed: `lint ok (44 files)`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.
- Wording search found no remaining standalone legacy model-summary labels. Remaining `OpenAI` matches are provider-name/configuration references that identify an explanation-summary provider, not a stock-selection engine.

## SaaS Legacy API Migration Gate - 2026-06-03 KST

Scope:

- Reviewed UI calls and server routing for legacy global `/api/watchlist`, `/api/scan`, and `/api/select`.
- Changed SaaS mode legacy global endpoint behavior from generic validation failure to explicit `410 LEGACY_ENDPOINT_GONE`.
- Added migration messages that point clients to tenant-scoped `/api/user/watchlist`, `/api/user/scan`, and `/api/user/select`.
- Added served-dashboard regression coverage to prevent direct legacy global calls when `user_auth_enabled=true`.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_web
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
```

Result:

- Web regression tests passed: `12` tests.
- Full unit test suite passed: `76` tests.
- Lint passed: `lint ok (44 files)`.
- Compile smoke passed for `vcb_alt` and `tests`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.

Specific cases verified:

- `GET/POST/DELETE /api/watchlist` return `410 LEGACY_ENDPOINT_GONE` in SaaS mode and point to `/api/user/watchlist`.
- `GET/POST /api/scan` return `410 LEGACY_ENDPOINT_GONE` in SaaS mode and point to `/api/user/scan`.
- `GET/POST /api/select` return `410 LEGACY_ENDPOINT_GONE` in SaaS mode and point to `/api/user/select`.
- Served dashboard JavaScript uses `endpoint('/api/...', '/api/user/...')` helper calls and contains no direct `api('/api/watchlist')`, `api('/api/scan')`, or `api('/api/select')` calls.

## Market Discovery Watchlist Boundary - 2026-06-03 KST

Scope:

- Reviewed starter watchlist seeding and manual ticker input against the market-wide discovery product direction.
- Disabled automatic starter watchlist seeding for market-wide and production SaaS flows.
- Moved manual ticker input into a collapsible secondary research drawer.
- Added an explicit optional starter research-list helper button instead of automatic browser tenant seeding.
- Added watchlist API metadata for `result_boundary`, `starter_helper_available`, and optional onboarding helper behavior.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_web
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
```

Result:

- Web regression tests passed: `10` tests.
- Full unit test suite passed: `74` tests.
- Lint passed: `lint ok (44 files)`.
- Compile smoke passed for `vcb_alt` and `tests`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.

Browser/mobile note:

- Attempted to start a local smoke server for in-app browser verification, but the command was blocked by the current approval/usage limit.
- Static UI regression coverage confirms the market-wide CTA appears in the first hero section, `.decision-area` is ordered before `.sidebar` on mobile, and the manual ticker input is in a secondary collapsible drawer.

## Live-Data-Required Sample Fallback Hard Gate - 2026-06-03 KST

Scope:

- Reviewed the production candidate-output path for places where sample/demo market-universe output could be returned as real research candidates.
- Added a hard gate so `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true` fails closed unless market-universe results are backed by Alpaca stock snapshots.
- Prevented stale sample scan-report cache and durable sample market snapshot rows from being served as fresh production candidate output.
- Kept sample universe fallback available only for local/demo mode where live-data-required is explicitly false.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_market_universe
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_saas_auth
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
```

Result:

- Market-universe regression tests passed: `6` tests.
- SaaS auth/queue regression tests passed: `21` tests.
- Full unit test suite passed: `72` tests.
- Lint passed: `lint ok (44 files)`.
- Compile smoke passed for `vcb_alt` and `tests`.
- `git diff --check` passed; Git only reported existing Windows LF-to-CRLF working-copy warnings.

Specific cases verified:

- Live-data-required market scans raise a clear fail-closed `ValidationError` instead of returning sample universe candidates.
- Fresh scan-report cache containing sample/demo output is deleted and not returned under live-data-required mode.
- Cached Alpaca snapshot data remains valid when the report source starts with `alpaca:`.
- Durable market snapshot rows containing sample/demo fallback are ignored by `/api/user/scan` snapshot reads when live-data-required mode is active.

## Readiness Wording Audit - 2026-06-03 KST

Scope:

- Searched the full repository for active wording that could imply external beta, unrestricted release, or 1000-user SaaS readiness.
- Replaced active external-beta/unrestricted-release phrasing with owner/operator-trial, external-release blocker, or historical gate wording.
- Preserved past implementation history only when explicitly labeled as historical.
- Kept `public_launch_ready=false` and `NOT_READY_FOR_1000_USER_SAAS` because those values communicate the current blocked state.

Commands run:

```powershell
rg -n -i "<requested external-beta, launch-ready, and 1000-user overstatement phrase set>" . --glob '!*.pyc' --glob '!__pycache__/**' --glob '!.git/**'
rg -n -i "<old unrestricted-release wording>" . --glob '!*.pyc' --glob '!__pycache__/**' --glob '!.git/**'
rg -n -i "owner/operator trial|owner-trial|operator-trial|external-release|unrestricted external" README.md RELEASE_DECISION.md QA_REPORT.md OPERATIONS.md DEPLOYMENT.md PUBLIC_DEPLOYMENT.md RELEASE_CRITERIA.md SAAS_IMPLEMENTATION_PLAN.md SECURITY_COMPLIANCE_1000_USER.md IMPLEMENTATION_PLAN.md
```

Result:

- The requested overstatement search returned no matches.
- The old unrestricted-release wording search returned no matches.
- Owner/operator-trial and external-release blocker wording is present in the primary readiness documents.
- Current readiness remains `public_launch_ready=false` and `NOT_READY_FOR_1000_USER_SAAS`.

## Market-Wide Discovery UI Realignment - 2026-06-03 KST

Scope:

- Read the web UI path and reoriented the first screen from manual watchlist scoring to market-wide discovery.
- Promoted the first-screen CTA to "Scan full market / latest candidates".
- Demoted manual ticker input to an optional research panel with API metadata that identifies it as secondary to market-wide discovery.
- Added visible scan freshness, provider source, data coverage, and fail-closed state cards.
- Expanded Korean mode for static labels, dynamic provider/status values, empty states, and candidate rationale text.
- Adjusted mobile ordering so the latest candidate results appear before the optional manual research panel.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_web
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests
node --check data\served_app_check.js
node --check data\served_detail_check.js
```

Browser smoke:

- Started a local sample market-universe web server with `VCB_ALT_SCAN_MODE=market_universe`, `VCB_ALT_DATA_PROVIDER=sample`, and `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=false`.
- English first screen showed market-wide discovery CTA, scan freshness, provider source, data coverage, fail-closed state, and optional manual research as secondary.
- Korean mode translated UI labels, provider/status values, empty states, and rationale text; no English primary UI copy remained.
- Scan CTA returned `7` scanned names and `3` selected research candidates in local sample mode.
- Desktop viewport `1280x800`: primary CTA and market-wide status were visible before manual research.
- Mobile viewport `390x820`: no horizontal overflow; selected candidate results appeared before the optional manual research panel.

Result:

- Lint passed: `lint ok (44 files)`.
- Served dashboard/detail JavaScript syntax checks passed.
- Web unit tests passed: `8` tests.
- Full unit test suite passed: `69` tests.
- Compile smoke passed for `vcb_alt` and `tests`.

Notes:

- Browser smoke initially exposed a sandbox-only cache write permission issue when the browser-spawned smoke server used the workspace `data` directory. The app path was re-run with a writable temp data directory and passed.
- This UI work does not change the production launch gate: public/paid SaaS remains blocked until live provider diagnostics, hosted load testing, operations drills, and legal review pass.

## Neon/Monitoring/Legal Operations Readiness - 2026-06-03 KST

Scope:

- Reviewed Neon restore, monitoring, operations, and legal handoff documents.
- Converted the Neon backup/restore drill into an executable staging procedure with migration drift checks, sample tenant integrity checks, RTO/RPO measurement, and rollback steps.
- Converted monitoring into incident runbooks for provider outage, worker failure, queue backlog, DB error, auth abuse, and rate-limit saturation.
- Reframed legal review as counsel handoff only; AI does not approve legal readiness.
- Updated Terms, Privacy, and Risk Disclosure draft status to owner/operator trial and legal-review pending.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app --timeout 20
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

Result:

- `overall_status=ok`.
- `release_channel=operator_trial`.
- `production_saas_ready=true`.
- `public_launch_ready=false`.
- `database_backend=postgresql`.
- `rate_limit_backend=database`.
- `queue_enabled=true`.
- `user_auth_enabled=true`.
- `worker_cron_enabled=true`.
- Provider warning remained: Alpaca credentials are configured but not live-verified; `/api/provider-diagnostics/alpaca` is still required before production scans.

Documentation updates:

- `NEON_BACKUP_RESTORE_DRILL.md`: staging restore, migration drift, sample tenant integrity, RTO/RPO, and rollback procedure documented.
- `MONITORING_ALERTING_PLAN.md`: incident runbooks documented.
- `OPERATIONS.md`: production incident entry points added.
- `LEGAL_REVIEW_PACKET.md`: counsel handoff and launch restrictions documented.
- `TERMS.md`, `PRIVACY.md`, `RISK_DISCLOSURE.md`: draft status and legal-review gate corrected.
- `rg` verification found no active stale beta-readiness or investment-action claims outside explicit prohibited-word/legal-blocker context. Remaining advice-related hits are PostgreSQL `advisory lock` technical references or legal prohibited-word lists.
- Lint passed: `lint ok (44 files)`.
- Typecheck passed: `type hints ok (415 objects)`.
- Full unit test suite passed: `68` tests.
- Compile/build smoke passed for `vcb_alt`, `tests`, `tools`, and `api`.

Remaining:

- Neon staging restore has not been executed because it requires operator Neon console/API access and a selected staging branch.
- Public, paid, or investment-advice-adjacent launch remains blocked pending counsel approval.

## Hosted Scan-Heavy 1000-User Load Test Gate - 2026-06-03 KST

Scope:

- Updated `tools/host_queue_load_test.py` so a hosted scan-heavy run can exercise registration/login, scan enqueue, protected worker trigger, job polling, snapshot reads, provider-health budget guards, provider failure visibility, queue depth, DB error counts, provider call deltas, worker completion counts, and cleanup of generated test accounts.
- Added a structured preflight-block report when required production secrets are not available to the test runner.
- Added default test-account cleanup for completed load-test flows to avoid leaving 1000 generated tenants in production.

Commands run:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --help
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load --confirm-provider-budget --expected-provider-calls 280 --max-provider-calls 350 --min-provider-budget-remaining 350 --snapshot-read-sample 1000 --out data\hosted_scan_heavy_1000_20260603.json
```

Production preflight checks:

- `GET /api/health`: `200`, healthy.
- `GET /api/provider-health`: `200`; Alpaca, Finnhub, Yahoo, and template providers reported `ready`; OpenAI and SEC were `not_configured`.
- `GET /api/release-status`: `200`; `release_channel=operator_trial`, `public_launch_ready=false`, `scan_queue_enabled=true`, `worker_configured=true`, and `worker_cron_enabled=true`.
- Manual signup preflight: `POST /api/auth/register` returned `201`; the test account was deleted with `DELETE /api/user/account?confirm=DELETE_MY_ACCOUNT`, which returned `200`.
- Worker protection preflight: `POST /api/admin/run-worker?limit=1` without a worker token returned `401`, confirming the endpoint is protected.

Hosted 1000-user result:

- Result file: `data/hosted_scan_heavy_1000_20260603.json`.
- Final decision: `NOT_READY_FOR_1000_USER_SAAS`.
- The 1000-user scan-heavy workload was not executed beyond safe preflight because the local test runner did not have `VCB_ALT_WORKER_TOKEN`.
- Request count executed by the tool before blocking: `3`.
- HTTP status counts: `200=3`, `2xx=3`, `4xx=0`, `5xx=0`.
- Overall latency: p50 `395.09ms`, p95 `421.47ms`, p99 `421.47ms`, max `421.47ms`.
- Stage latency:
  - `health`: p50/p95/p99 `395.09ms`.
  - `provider_health_before`: p50/p95/p99 `421.47ms`.
  - `release_status`: p50/p95/p99 `392.1ms`.
- Registration/login/enqueue: `0` attempted in the guarded run because protected worker execution was impossible.
- Worker trigger/completion: `0` processed, `0` failed, `0` completed.
- Job polling: `0` jobs.
- Snapshot reads: `0` attempted.
- Queue depth: available but no authenticated admin queue read was executed in the guarded run.
- DB error count: `0`.
- Provider failure count: `0`.
- Provider call count delta: not measured because no worker/provider-heavy scan was triggered.
- Provider budget guard: blocked provider calls before execution; no provider budget was consumed by the hosted load command.

Interpretation:

- The tool for a real hosted 1000-user scan-heavy completion test now exists and records the required metrics.
- This run does not prove 1000-user operability because the protected worker trigger was not executed.
- The production API appears configured for operator-trial SaaS mode, but the operator-held worker token is required to prove scan enqueue, worker completion, polling, and snapshot read under 1000-user load.
- Current status remains `NOT_READY_FOR_1000_USER_SAAS` until the hosted command completes with `load_test_passed=true` and provider budgets remain within guard limits.

## Worker-Owned Durable Market Scan Snapshot - 2026-06-03 KST

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest tests.test_saas_auth tests.test_db tests.test_web
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests
```

Results:

- Added durable `market_scan_snapshots` storage for worker-owned market-universe scan reports.
- Production SaaS `/api/user/scan` now reads the latest fresh snapshot or returns `202` with queued/pending snapshot job status.
- Worker processing now claims market snapshot jobs before tenant jobs and writes report, selected candidates, provider metadata, freshness, and failures.
- Added `/api/jobs/market-scan/{id}` for market snapshot job status.
- Added retry scheduling, stale-running recovery, and `dead_letter` handling for market snapshot jobs.
- Added admin queue-status visibility for market snapshot counts and latest job state.
- Added regression coverage for first-request enqueue, idempotent pending response, worker refresh, fresh snapshot read, user evaluation persistence, retry scheduling, and dead-letter recovery.
- Targeted SaaS/DB/web tests passed: `26` tests.
- Full unit test suite passed: `62` tests.
- Lint passed: `lint ok (42 files)`.
- Typecheck passed: `type hints ok (378 objects)`.
- Compile/build smoke passed.
- Production deploy completed and `https://stockscreeningver10.vercel.app` was aliased to the new build.
- Production `POST /api/user/scan` returned `202` with `state=queued`, a `market_*` job id, and no `items`, confirming the user request no longer executes the provider-heavy market scan directly.
- Production `GET /api/jobs/market-scan/{id}` returned the queued snapshot job status.
- Production `GET /api/admin/queue-status` exposed `market_scan_snapshots` counts and latest queued job metadata.
- Production protected worker trigger was not completed from this workstation because the local shell does not have `VCB_ALT_WORKER_TOKEN`; the endpoint correctly returned `401 Worker authentication is required`.

Remaining production note:

- This structural change prevents concurrent users from directly duplicating provider-heavy scans, but live market results still require Alpaca diagnostics to return `ready=true`.
- A hosted worker completion verification still requires the operator-held worker token or Vercel Cron execution.

## Alpaca Credential Diagnostics Implementation - 2026-06-03 KST

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest tests.test_market_universe tests.test_web
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests
```

Results:

- Added secret-safe Alpaca diagnostics at `/api/provider-diagnostics/alpaca`.
- Diagnostics checks expected Vercel env variable names, Paper Trading API acceptance, Live Trading API acceptance, and Market Data snapshot acceptance for the configured feed.
- Diagnostics returns status/classification/next actions only; it does not return Alpaca key or secret values.
- Targeted tests passed: `11` tests.
- Full test suite passed: `60` tests.
- Lint passed: `lint ok (42 files)`.
- Typecheck passed: `type hints ok (365 objects)`.
- Compile/build smoke passed.
- Production deploy completed and `https://stockscreeningver10.vercel.app` was aliased to the new build.
- Production `/api/provider-diagnostics/alpaca` returned `classification=key_context_mismatch_or_invalid`, `ready=false`, `feed=iex`, and `HTTP 401` for Paper Trading, Live Trading, and Market Data snapshot checks.
- Production `/api/user/scan` was re-tested after deploy and still failed closed with Alpaca HTTP 401. No sample fallback candidates were returned.
- Required operator action: regenerate the Alpaca Key ID and Secret Key as one matching pair, update both Vercel Production variables, redeploy, rerun `/api/provider-diagnostics/alpaca`, and only then rerun `/api/user/scan`.

## Market-Universe Algorithm Verification - 2026-05-26 KST

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest tests.test_market_universe tests.test_web tests.test_cli tests.test_saas_auth
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools
```

Results:

- Targeted regression tests passed: `30` tests.
- Full unit test suite passed: `58` tests.
- Lint passed: `lint ok (42 files)`.
- Typecheck passed: `type hints ok (359 objects)`.
- Compile/build smoke passed.
- Local HTTP smoke passed with `VCB_ALT_SCAN_MODE=market_universe`; `/api/scan` returned `scan_mode=market_universe`, sample fallback metadata, and selected `VST`, `PLTR`, `MSTR`.
- Production configuration smoke after deploy returned `scan_mode=market_universe`, `external_api_enabled=true`, `market_universe_live_ready=true`, Alpaca intraday ready, and Finnhub research ready.
- First production live scan attempt failed at Alpaca assets authentication with `HTTP 401`; code now retries both Alpaca paper and live trading asset endpoints before reporting credential failure.

Remaining live-data note:

- Local verification intentionally used sample fallback because local Alpaca/Finnhub secrets were not loaded.
- Production must set `VCB_ALT_EXTERNAL_API_ENABLED=true`, Alpaca credentials, Finnhub or CSV enrichment, and `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true` before the service can truthfully claim live all-market research candidate output.

## Current Status Summary - 2026-05-22 KST

This report is append-only. Earlier sections preserve historical blockers from prior gates; the current state is:

- Neon PostgreSQL is connected in Vercel Production.
- Production SaaS mode reports PostgreSQL, per-user auth, database-backed rate limiting, scan queue, worker token, and worker cron configured.
- Production SaaS smoke passed for registration, tenant watchlist, scan queue, protected worker processing, and job status lookup.
- Hosted `/api/health` load smoke passed after cutover with `1000/1000` HTTP 200 responses and `0` errors.
- Remaining launch blockers are scan-heavy hosted queue/provider load tests, monitoring/alerts, Neon backup/restore drill, auth hardening, WAF/proxy hardening, and legal-reviewed launch documents.

## 1. Commands Run

Dependency install:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m pip install -r requirements.txt
```

Type check, lint, tests, build:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
node --check deploy\cloudflare-worker.js
```

Automatic market-data flow:

```powershell
$env:VCB_ALT_DATA_PROVIDER='yahoo'
$env:VCB_ALT_EXTERNAL_API_ENABLED='true'
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m vcb_alt evaluate AAPL --json
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m vcb_alt scan --json
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m vcb_alt select --json
```

Public web mode:

```powershell
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_PUBLIC_WEB_ENABLED=true
VCB_ALT_WEB_ACCESS_TOKEN=local-demo-token-123456
python -m vcb_alt web --host 127.0.0.1 --port 8766
```

API checks:

```powershell
Invoke-WebRequest http://127.0.0.1:8766/api/health
Invoke-WebRequest http://127.0.0.1:8766/api/config
Invoke-WebRequest http://127.0.0.1:8766/api/select?token=local-demo-token-123456
```

Benchmark:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m vcb_alt benchmark --repeat 1000 --json
```

Production deployment:

```powershell
npx.cmd vercel deploy --prod --yes -e VCB_ALT_DATA_PROVIDER=yahoo -e VCB_ALT_EXTERNAL_API_ENABLED=true -e VCB_ALT_PUBLIC_WEB_ENABLED=true -e VCB_ALT_WEB_ACCESS_TOKEN=<operator-token> -e VCB_ALT_DATABASE_URL=sqlite:////tmp/vcb_alt.db -e VCB_ALT_DATA_DIR=/tmp/vcb_alt_data -e VCB_ALT_LOG_DIR=/tmp/vcb_alt_logs
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/health
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/config
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/config?token=<operator-token>
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/select?token=<operator-token>
```

## 2. Results

- Dependency install: passed. No third-party runtime packages are required.
- Type check: passed, `type hints ok (166 objects)`.
- Lint: passed, `lint ok (28 files)`.
- Tests: passed, `27` tests.
- Build/syntax check: passed for `vcb_alt`, `tests`, `tools`, and `api`.
- Cloudflare Worker syntax check: passed with `node --check deploy\cloudflare-worker.js`.
- Vercel production deployment: passed. Production alias is `https://stockscreeningver10.vercel.app`.
- Vercel health check: passed, `/api/health` returned `200`.
- Vercel auth gate: passed, `/api/config` without token returned `401`.
- Vercel authenticated config: passed, `/api/config?token=...` returned `200`.
- Vercel authenticated selection: passed, `/api/select?token=...` returned `200`.
- Automatic Yahoo market-data fetch: passed for `AAPL`.
- Watchlist selection with automatic market data: passed, no provider failures.
- Public token gate: passed. `/api/health` is public, `/api/config` without token returns `401`, `/api/select?token=...` succeeds.
- Browser verification: passed. The in-app browser loaded `http://127.0.0.1:8766/?token=local-demo-token-123456` and showed Yahoo data, AAPL/MSTR, and Technical Momentum selection state.
- Benchmark: passed, `7000` evaluations in `189.48 ms`, `36943.52` evaluations/second, `0.0271 ms` per evaluation.

## 3. Failed Results And Causes

- Stooq no-key live fetch reached the network but returned an API-key/captcha instruction page instead of OHLCV CSV.
- Initial shell-network run without escalation was blocked by local sandbox socket permissions.
- PowerShell `Start-Process` failed in this environment due duplicate `Path`/`PATH` environment keys; the web server was verified through a persistent background process instead.
- Cloudflare Worker deployment is blocked by Cloudflare account email verification: `10034: You need to verify your email address to use Workers`.
- Docker local build/run was not verified because Docker Desktop daemon is not running.

## 4. Problems Fixed

- Added `yahoo` automatic chart provider for no-key market-data fetch.
- Kept `stooq` as optional CSV provider and added a clear error when API key/captcha is required.
- Added local cache, timeout, parse validation, and provider failure handling.
- Added technical momentum scoring so price/volume-only providers can produce honest candidates instead of all-zero fundamental scores.
- Added public web token guard and tested unauthorized access.
- Added Vercel serverless adapter and deployed the token-protected production alias.
- Added configurable data/log directories so serverless runtimes can write under `/tmp`.

## 5. Remaining Problems

- Public mode is token-protected demo access, not per-user authentication.
- SQLite is acceptable for local/private beta, but not for 1000-user multi-tenant SaaS.
- Yahoo/Stooq data is price/volume only; fundamentals, news, short interest, options, and analyst revisions are not automated yet.
- Legal-reviewed Terms, Privacy, and investment-risk disclosures are still required before public financial-service launch.
- No load test has been executed against a deployed public host.
- Vercel serverless storage is ephemeral. Watchlist/cache state can reset on cold starts or redeploys.

## 6. Actual User Flow Test Result

Passed:

1. App starts locally.
2. Watchlist loads with 7 tickers.
3. Automatic market-data provider fetches/caches data.
4. Scan returns results without provider failures.
5. Selection returns current candidates.
6. Web dashboard loads in browser with token.
7. API rejects unauthorized access.
8. Operations status and failures endpoint load.
9. Production Vercel dashboard loads in the in-app browser with token.
10. Production selection API returns live Yahoo-based candidates with zero provider failures.

Observed automatic selection:

- `AAPL`: Technical Momentum, score `72`, high-scoring watchlist candidate, suggested size `15.73%`, data as of `2026-05-18`.
- `MSTR`: Technical Momentum, score `61`, watchlist candidate, suggested size `14.84%`, data as of `2026-05-18`.
- Total suggested size: `30.57% / 75.0%`.

## 7. Release Readiness Judgment

READY_FOR_PRIVATE_BETA.

Historical 2026-05-18 judgment at that time: the app was considered usable as a controlled, token-protected demo. Current status is superseded by the 2026-06-03 owner/operator-trial judgment and Alpaca live-scan blocker.

## 8. 2026-05-19 UX Redesign Verification

Additional commands run after the user-supplied UI direction and external stock-screener UX research:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
```

Results:

- Type check: passed, `type hints ok (166 objects)`.
- Lint: passed, `lint ok (28 files)`.
- Tests: passed, `28` tests.
- Build/syntax check: passed for `vcb_alt`, `tests`, `tools`, and `api`.
- Local web health check: passed on `http://127.0.0.1:8770/api/health`.
- Browser verification: passed. The in-app browser loaded `http://127.0.0.1:8770/`, rendered the decision-first dashboard, showed final candidate cards, actionable setups, monitor/excluded names, and opened the score detail modal for `VST`.

UX-specific conclusion:

- The user-supplied dark operations-desk direction was implemented without hardcoded ticker scores, Tailwind CDN, Google Fonts, Material Symbols, or Chart.js.
- The product direction remains focused on precise candidate selection, rationale, data freshness, and operational trust indicators rather than becoming a generic filter-heavy screener.

Production redeploy verification:

```powershell
npx.cmd vercel deploy --prod --yes -e VCB_ALT_DATA_PROVIDER=yahoo -e VCB_ALT_EXTERNAL_API_ENABLED=true -e VCB_ALT_PUBLIC_WEB_ENABLED=true -e VCB_ALT_WEB_ACCESS_TOKEN=<operator-token> -e VCB_ALT_DATABASE_URL=sqlite:////tmp/vcb_alt.db -e VCB_ALT_DATA_DIR=/tmp/vcb_alt_data -e VCB_ALT_LOG_DIR=/tmp/vcb_alt_logs
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/health
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/config?token=<operator-token>
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/select?token=<operator-token>
```

Production results:

- Vercel production deployment: passed. The existing alias `https://stockscreeningver10.vercel.app` now points to the redesigned dashboard deployment.
- Production health API: passed, `200`.
- Production authenticated config API: passed, `200`.
- Production authenticated selection API: passed, `200`.
- Production browser verification: passed. The deployed page rendered final candidate cards, actionable and excluded groups, and the score report modal.
- Screenshot artifact: `vercel-ui-redesign-verified.png`.

## 9. 2026-05-19 Public-Beta Safety Layer Verification

Additional changes verified:

- Added SaaS-safe `public_label` values while preserving internal `status` and `decision_label` fields.
- Added `/api/provider-status` with provider capabilities, timeout, cache TTL, and non-secret warnings.
- Added starter `TERMS.md`, `PRIVACY.md`, and `RISK_DISCLOSURE.md`.
- Linked Risk Disclosure, Privacy, and Terms from the dashboard footer.
- Updated `IMPLEMENTATION_PLAN.md` and `SAAS_IMPLEMENTATION_PLAN.md` before implementing this gate.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
```

Results:

- Type check: passed, `type hints ok (168 objects)`.
- Lint: passed, `lint ok (28 files)`.
- Tests: passed, `29` tests.
- Build/syntax check: passed for `vcb_alt`, `tests`, `tools`, and `api`.

Production redeploy verification:

```powershell
npx.cmd vercel deploy --prod --yes -e VCB_ALT_DATA_PROVIDER=yahoo -e VCB_ALT_EXTERNAL_API_ENABLED=true -e VCB_ALT_PUBLIC_WEB_ENABLED=true -e VCB_ALT_WEB_ACCESS_TOKEN=<operator-token> -e VCB_ALT_DATABASE_URL=sqlite:////tmp/vcb_alt.db -e VCB_ALT_DATA_DIR=/tmp/vcb_alt_data -e VCB_ALT_LOG_DIR=/tmp/vcb_alt_logs
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/health
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/provider-status?token=<operator-token>
Invoke-WebRequest https://stockscreeningver10.vercel.app/api/select?token=<operator-token>
```

Production results:

- Vercel production deployment: passed. Alias `https://stockscreeningver10.vercel.app` was updated.
- Production health API: passed, `200`.
- Production provider-status API: passed, `200`, returned `yahoo` EOD price/volume capability metadata and no secrets.
- Production selection API: passed, `200`, returned `public_label` and `scoring_version`.
- Historical production browser verification: passed. Dashboard showed safety copy, legal links, public labels, and scoring version.
- Risk disclosure page verification: passed.
- Historical screenshot artifact: `vercel-safety-verified.png`.

## 10. 2026-05-19 1000-User SaaS Boundary Verification

Implemented:

- Per-user auth primitives with PBKDF2 password hashing and opaque session tokens.
- Tenant-scoped SaaS tables for tenants, users, sessions, and user watchlists.
- Bearer-session APIs for register/login/me/user watchlist.
- Basic in-process rate limit guard for the current stdlib API server.
- PostgreSQL target migration at `migrations/postgres/001_saas_core.sql`.
- Local 1000-user load simulation tool at `tools/load_test.py`.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\load_test.py --users 1000 --tickers 30
```

Results:

- Type check: passed, `type hints ok (197 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `34` tests.
- Build/syntax check: passed.
- Local load simulation: passed.
- Load simulation users: `1000`.
- Load simulation evaluations: `30000`.
- Load simulation throughput: `1706.81` evaluations/second.
- Load simulation p95 user flow: `10.957` ms.
- Load simulation errors: `0`.
- Tenant isolation: `passed`.

Remaining before unrestricted 1000-user public operation:

- Wire a live managed PostgreSQL database and run the migration there.
- Replace in-process rate limiting with Redis or managed edge rate limits.
- Add OAuth/email verification and MFA for admins.
- Run deployed-host HTTP concurrency tests.
- Run provider outage/budget tests and backup/restore drills.

Production redeploy verification:

- Vercel production deployment: passed. Alias `https://stockscreeningver10.vercel.app` was updated.
- Production health API: passed, `200`.
- Production SaaS readiness API: passed, returned updated partial statuses for auth, tenant isolation, API, database, and load testing.
- Production `/api/auth/login` with user auth disabled returned `400` with `User authentication is not enabled.`, which is the expected safe default.

## 11. 2026-05-19 Ticker Detail Analysis Verification

Implemented:

- Ticker detail pages at `/ticker/<ticker>`.
- Detail API at `/api/ticker-analysis?ticker=<ticker>`.
- Five-year daily price/volume chart payloads with provider freshness and `is_realtime=false` unless a future provider explicitly supports real-time data.
- Sector/industry profile fields with curated fallback for the default watchlist.
- Selection rationale, current status, metrics, and expert-consensus analysis sections.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\load_test.py --users 1000 --tickers 30
```

Results:

- Type check: passed, `type hints ok (204 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `36` tests.
- Build/syntax check: passed.
- Local 1000-user simulation: passed, `30000` evaluations, `0` errors, tenant isolation `passed`.
- Local browser verification: passed. Clicking a selected candidate navigated to `/ticker/PLTR`; the detail page rendered a five-year price/volume chart, industry, selection reason, current status metrics, and expert consensus.
- Screenshot artifact: `ticker-detail-local-verified.png`.
- Production browser verification: passed. The deployed detail page opened at `https://stockscreeningver10.vercel.app/ticker/AAPL?token=...` with page title `AAPL Analysis - VCB-Alt`.
- Production detail API verification: passed. `/api/ticker-analysis?ticker=AAPL&token=...` returned `200`, ticker `AAPL`, sector `Technology`, industry `Consumer Electronics`, five-year range `5y`, `1256` chart points, `is_realtime=false`, and a populated selection rationale.
- Production limitation disclosure: passed. The detail API labels Yahoo/Stooq market data as EOD/delayed rather than tick-by-tick real-time, which keeps the public product truthful until a licensed real-time provider is integrated.
- Post-comment verification: passed. After adding inline comments that document the delayed/EOD data boundary and evaluator reuse, type check, lint, and the full `36`-test suite still pass.

## 12. 2026-05-20 Responsive And Bilingual UI Verification

Implemented:

- Responsive dashboard and ticker detail layout guards for mobile and browser zoom.
- Box-safe wrapping for panels, metric boxes, cards, badges, buttons, table cells, and long rationale text.
- Clean app-standard system font stack with Korean-friendly fallbacks.
- Persisted Korean/English language toggles on the dashboard and ticker detail page.
- Mobile table-card labels for scan results.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
```

Results:

- Type check: passed, `type hints ok (204 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `37` tests.
- Build/syntax check: passed.
- Mobile ticker detail browser check: passed at `390x844`. Korean mode rendered, chart existed, no horizontal overflow, and no inspected panel/metric/chart box escaped the viewport.
- Mobile dashboard browser check: passed at `390x844`. Korean mode rendered, `3` candidate cards loaded, mobile row labels rendered as Korean, no horizontal overflow, and no inspected card/panel/table box escaped the viewport.
- Screenshot artifacts: `ticker-detail-responsive-ko.png`, `dashboard-responsive-ko.png`.
- Production deployment: passed. Vercel aliased the update to `https://stockscreeningver10.vercel.app`.
- Production CSS smoke: passed. `/assets/app.css` includes the Korean font fallback, overflow wrapping, and mobile table-card CSS.
- Production mobile detail browser check: passed at `390x844`. Korean mode rendered, chart existed, no horizontal overflow, and no inspected panel/metric/chart box escaped the viewport.
- Production screenshot artifact: `production-ticker-detail-responsive-ko.png`.

## 13. 2026-05-20 Production Deployment Verification

Deployment:

- Vercel production deploy: passed.
- Deployment URL: `https://stockscreeningver10-3qtrt3py6-2010180016y-7667s-projects.vercel.app`
- Production alias: `https://stockscreeningver10.vercel.app`

Pre-deploy checks:

- Type check: passed, `type hints ok (204 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `37` tests.
- Build/syntax check: passed.

Post-deploy checks:

- `/api/health`: passed, `200`.
- `/assets/app.css`: passed, includes Korean font fallback, overflow wrapping, and mobile table-card CSS.
- `/api/ticker-analysis?ticker=PLTR`: passed, `200`, ticker `PLTR`, range `5y`, `1256` chart points, industry `Software - Infrastructure`, `is_realtime=false`.
- Production mobile browser check: passed at `390x844`. Korean mode rendered, chart existed, no horizontal overflow, and no inspected panel/metric/chart box escaped the viewport.
- Screenshot artifact: `production-deploy-20260520-mobile-ko.png`.

## 14. 2026-05-20 Data Quality Gate Verification

Implemented:

- Added manual enrichment overlay support at `data/enrichment.csv` for Yahoo/Stooq market snapshots.
- Added `data/enrichment.example.csv`.
- Added data coverage scoring across market, fundamentals/earnings, catalyst/news, and positioning.
- Blocked price/volume-only Yahoo/Stooq scans from final selection until coverage reaches `60/100`.
- Added data coverage fields to evaluation and detail-page output.
- Bumped scoring version to `mvp-market-v0.4.0`.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
```

Results:

- Type check: passed, `type hints ok (208 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `38` tests.
- Build/syntax check: passed.
- Price-only Stooq/Yahoo-derived market snapshot: blocked from final entry despite a high Technical Momentum score.
- Yahoo snapshot plus operator enrichment CSV: passed the data coverage gate and became eligible.
- Production deploy attempt: blocked by environment usage limit before Vercel could run. The local code and tests are ready, but this data-quality gate has not been redeployed to the production alias in this run.
- Production redeploy retry: passed. Vercel aliased deployment `stockscreeningver10-38s5ogzn3-2010180016y-7667s-projects.vercel.app` to `https://stockscreeningver10.vercel.app`.
- Production health check: passed, `/api/health` returned `200`.
- Production detail API: passed, `PLTR` returned scoring version `mvp-market-v0.4.0`, `can_enter=false`, data coverage `35/100`, and label `price-volume-only`.
- Production provider status: passed, provider `yahoo`, `enrichment_available=false`, and warnings state that price-only scans are blocked from final selection.
- Production final selection API: passed, selected count `0`, rejected count `7`, provider `yahoo`.

## 15. 2026-05-20 Research Data Provider Verification

Implemented:

- Added a research-data provider layer separate from Yahoo/Stooq market data.
- Added `VCB_ALT_RESEARCH_DATA_PROVIDER=csv|finnhub|finnhub_csv`.
- Added `VCB_ALT_FINNHUB_API_KEY` and `VCB_ALT_RESEARCH_DATA_CACHE_TTL_HOURS`.
- Added Finnhub enrichment support for fundamentals, earnings surprise, recent news catalysts, insider transactions, short interest, and option-chain open interest.
- Added option-chain fields: `call_open_interest`, `put_open_interest`, and `put_call_ratio`.
- Kept `csv` as the safe default so no external research API is called without explicit credentials.
- Added cached Finnhub fixture tests, avoiding live network or paid API dependency in CI.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests -v
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall vcb_alt tests tools api
```

Results:

- Type check: passed, `type hints ok (221 objects)`.
- Lint: passed, `lint ok (33 files)`.
- Tests: passed, `39` tests.
- Build/syntax check: passed.
- Finnhub cached fixture enrichment: passed. Fundamentals, earnings surprise, news catalyst, insider purchase activity, short interest, and option-chain open interest were applied over a Yahoo market snapshot.
- Secret exposure guard: passed. Provider status does not expose API key names or values.
- Production deployment: passed. Vercel aliased deployment `stockscreeningver10-ivtlodw29-2010180016y-7667s-projects.vercel.app` to `https://stockscreeningver10.vercel.app`.
- Production health check: passed, `/api/health` returned `200`.
- Production provider status: passed, provider `yahoo`, research provider `csv`, research capabilities include fundamentals and options, and no API key text leaked.
- Production detail API: passed, `PLTR` remains `can_enter=false` with data coverage `35/100` and label `price-volume-only`, which is expected until CSV enrichment or a Finnhub key is configured.

## 16. 2026-05-20 Full Data + AI Layer Verification

Implemented:

- Added optional Alpaca intraday snapshot overlay for near-real-time quote/trade/minute-bar context.
- Added Finnhub analyst rating trend parsing.
- Added optional SEC submissions metadata for latest filing date/type/URL and recent filing catalyst detection.
- Added deterministic explanation summary output and optional OpenAI Responses API mode with fallback to template summary.
- Added ticker detail UI panel for explanation summary plus intraday, short-interest, option put/call, and analyst-score metrics.
- Updated `.env.example`, README, product requirements, implementation plan, and changelog.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall -q vcb_alt tests tools
```

Results:

- Lint: passed, `lint ok (34 files)`.
- Type check: passed, `type hints ok (243 objects)`.
- Tests: passed, `40` tests.
- Build/syntax check: passed.
- Full data fixture: passed. Yahoo daily chart data, Alpaca intraday snapshot, Finnhub fundamentals/news/short/options/analyst data, and SEC filings were applied without live network calls.
- Explanation summary fixture: passed. `/api/ticker-analysis` returns a template summary by default and includes risk/data-quality limitations.
- Local browser verification: passed. `/ticker/PLTR` rendered the explanation summary panel, new status metrics, and no horizontal overflow.
- Production deployment: passed. Vercel deployment `stockscreeningver10-q4kz5cp18-2010180016y-7667s-projects.vercel.app` was aliased to `https://stockscreeningver10.vercel.app`.
- Production smoke: passed. `/api/health` returned `200`; provider status shows `provider=yahoo`, `research_data_provider=csv`, `intraday_data_provider=none`, `ai_summary_provider=template`; `/api/ticker-analysis?ticker=PLTR` returns scoring version `mvp-market-v0.5.0` and template explanation summary.
- Remaining production note: provider keys are not present in this workspace, so live Alpaca/Finnhub/OpenAI calls are structurally ready but not enabled until the operator configures credentials.

## 17. 2026-05-20 Operator Trial Finalization

Implemented:

- Added `/api/release-status` for deployed release self-reporting.
- Added `OPERATOR_TRIAL_GUIDE.md` with the owner usage URL, workflow checklist, provider mode, and public-launch blockers.
- Updated README, CHANGELOG, and RELEASE_DECISION for the owner pre-user usage build.

Commands run:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\lint.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' tools\typecheck.py
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m unittest discover -s tests
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m compileall -q vcb_alt tests tools api
```

Results:

- Lint: passed, `lint ok (34 files)`.
- Type check: passed, `type hints ok (244 objects)`.
- Tests: passed, `40` tests.
- Build/syntax check: passed.
- Local release API: passed, `release_channel=operator_trial`, `user_trial_ready=true`, `public_launch_ready=false`.
- Production deployment: passed. Vercel deployment `stockscreeningver10-qqroswqsv-2010180016y-7667s-projects.vercel.app` was aliased to `https://stockscreeningver10.vercel.app`.
- Production smoke: passed. `/api/health=200`, `/api/release-status` returns `operator_trial`, and `/api/ticker-analysis?ticker=PLTR` returns `mvp-market-v0.5.0` with template explanation summary.

## 18. 2026-05-20 Alpaca Production Key Check

Implemented:

- Added `intraday_error` to ticker analysis output so provider failures are visible instead of silently showing zero intraday price.
- Added Alpaca HTTP error handling for authentication, rate-limit, and malformed-response cases.
- Added Alpaca 401 troubleshooting notes to `PROVIDER_KEYS_SETUP.md`.

Results:

- Vercel Production env vars exist for Alpaca intraday provider, key, secret, feed, and cache TTL.
- Production redeploy passed and was aliased to `https://stockscreeningver10.vercel.app`.
- Release status passed: `intraday_provider=alpaca`, `intraday_ready=true`.
- Live PLTR ticker-analysis returned `intraday_error="Alpaca rejected the request with HTTP 401..."`.
- Interpretation: the app is reading Alpaca env vars, but Alpaca rejected the credential pair or selected account/feed context. Regenerate or re-enter the matching Alpaca Key ID and Secret Key.

## 19. 2026-05-21 Finnhub Production Key Check

Deployment:

- Redeployed production with `VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub`.
- Disabled Alpaca intraday overlay for the owner trial build with `VCB_ALT_INTRADAY_DATA_PROVIDER=none` to avoid the earlier Alpaca 401 blocking interpretation.
- Kept AI summaries on the safe template provider.

Production smoke result:

- `/api/health`: passed, `200`.
- `/api/release-status`: passed, `release_channel=operator_trial`.
- Research provider: passed, `finnhub`.
- Research ready: passed, `true`.
- Provider research configured: passed, `true`.
- `/api/ticker-analysis?ticker=PLTR`: passed.
- PLTR source: `yahoo+finnhub`.
- PLTR data coverage: `100/100`, `multi-source`.
- PLTR can enter final candidate set: `true`.
- Analyst score populated: `63.16`.
- Provider warnings: none.

Remaining note:

- Short interest and options put/call ratio returned `0` for PLTR in this smoke check. The provider key is working, but not every Finnhub endpoint returns populated data for every ticker/account/plan.

## 20. 2026-05-21 Alpaca Recheck

Deployment:

- Redeployed production with `VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca`.
- Kept `VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub`.
- Kept AI summaries on the safe template provider.

Production smoke result:

- `/api/health`: passed, `200`.
- Release status: passed, `release_channel=operator_trial`.
- Research provider: passed, `finnhub`, `research_ready=true`.
- Intraday provider: configured as `alpaca`, `intraday_ready=true`.
- Provider intraday configuration: `true`.
- `/api/ticker-analysis?ticker=PLTR`: passed.
- PLTR source: `yahoo+alpaca-intraday+finnhub`.
- PLTR data coverage: `100/100`.
- PLTR can enter final candidate set: `true`.
- Alpaca intraday result: failed with `HTTP 401`.

Interpretation:

- The app is reading the Alpaca env vars and attempting the Alpaca request.
- Alpaca is rejecting the credential pair or account/feed context.
- Finnhub remains healthy, so the owner trial can continue with multi-source research coverage even while Alpaca is unresolved.

## 21. 2026-05-21 Operator Trial Security and Speed Stabilization

Scope:

- Re-read the deployment entrypoint, web router, provider layer, scoring path, release-status reporting, tests, and operator documents before changing code.
- Updated implementation and operator documents to reflect the current owner-trial state: Yahoo market data, Finnhub research enrichment, Alpaca intraday disabled until its HTTP 401 is resolved, and template AI summaries.
- Added code comments at the provider/detail boundary where duplicate paid or limited provider calls are intentionally avoided.

Implemented:

- Reused the already-enriched ticker snapshot inside `/api/ticker-analysis` profile generation so a detail-page request does not call the same market/research provider twice.
- Cached Vercel serverless runtime bootstrap configuration for warm processes to avoid repeating config loading and database bootstrap work on every warm request.
- Hardened token-gated trial cookies by adding `Secure` when the request arrives through HTTPS forwarding headers.
- Fixed release-status intraday readiness so `intraday_ready=false` when the selected intraday provider is `none`, even if stale Alpaca keys still exist in the deployment environment.

Local verification:

- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py`: passed, `lint ok (34 files)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py`: passed, `type hints ok (246 objects)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests tools api`: passed.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests`: passed, `40` tests.
- Local web smoke on `127.0.0.1:8793`: passed for health, release status, scan, and selection path with `release_channel=operator_trial`, `user_trial_ready=true`, `public_launch_ready=false`, `intraday_provider=none`, `intraday_ready=false`, and `scan_count=7`.

Production deployment:

- Deployed production build `dpl_HTTYjmssPW8z61JxhS74ee1qV2t2`.
- Production URL: `https://stockscreeningver10.vercel.app`.
- Production data mode: `VCB_ALT_DATA_PROVIDER=yahoo`, `VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub`, `VCB_ALT_INTRADAY_DATA_PROVIDER=none`, `VCB_ALT_AI_SUMMARY_PROVIDER=template`.

Production smoke result:

- `/api/health`: passed, `200`.
- `/api/release-status`: passed, `release_channel=operator_trial`, `user_trial_ready=true`, `public_launch_ready=false`.
- Research provider: `finnhub`, `research_ready=true`.
- Intraday provider: `none`, `intraday_ready=false`.
- `/api/ticker-analysis?ticker=PLTR`: passed.
- PLTR source: `yahoo+finnhub`.
- PLTR data coverage: `100/100`.
- PLTR decision: `can_enter=true`, score `55`, archetype `AI Pick & Shovel`.
- PLTR profile: `Technology / Software - Infrastructure`.
- PLTR chart: `5y`, `1256` daily points.
- Explanation summary layer: `template summary`.
- `/api/select`: passed with `2` selected candidates and `0` failures.

Release judgment:

- The build is usable for the operator's private trial and review workflow.
- It is still not ready for a fully public 1000-user SaaS launch because production per-user auth, PostgreSQL cutover, tenant isolation in the public deployment, durable rate limiting, queue-backed scans, and real load testing remain launch blockers.

## 22. 2026-05-21 SaaS Readiness Implementation Pass

Implemented:

- Added optional PostgreSQL runtime support behind `postgresql://` / `postgres://` `DATABASE_URL` values.
- Added PostgreSQL migration tables for durable rate-limit events and background scan jobs.
- Added `VCB_ALT_PRODUCTION_SAAS_MODE=true` guard. The app now refuses to start public SaaS mode unless PostgreSQL, per-user auth, database-backed rate limiting, and scan queue are enabled together.
- Added database-backed rate limiting so serverless/warm-process replicas share one request budget through the database.
- Added tenant-scoped scan queue APIs:
  - `POST /api/jobs/scan`
  - `GET /api/jobs`
  - `GET /api/jobs/{id}`
- Added `python -m vcb_alt worker run-once` to process queued scan jobs.
- Blocked legacy global `/api/watchlist`, `/api/scan`, and `/api/select` APIs when per-user auth is enabled.
- Added hosted load-test tool `tools/host_load_test.py`.

Local verification:

- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py`: passed, `lint ok (36 files)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py`: passed, `type hints ok (277 objects)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests`: passed, `43` tests.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests tools api`: passed.
- SaaS smoke flow passed: register user, add tenant watchlist, enqueue scan job, run worker, complete job with `3` evaluated tickers.
- Local 1000-user load simulation passed:
  - Users: `1000`
  - Tickers per user: `30`
  - Evaluations: `30000`
  - Elapsed: `23.786s`
  - Throughput: `1261.24 evals/s`
  - P95 user flow: `13.892ms`
  - Errors: `0`
  - Tenant isolation: `passed`

Production environment check:

- Vercel Production currently has Finnhub and Alpaca-related provider variables.
- Vercel Production does **not** currently have a PostgreSQL `DATABASE_URL`.
- Therefore `VCB_ALT_PRODUCTION_SAAS_MODE=true` cannot be safely enabled yet.
- Two deployment attempts with the new code did not replace the main domain: one remained `Initializing`, another remained `Queued`. The main domain stayed healthy on the previous ready deployment.

Hosted load-test status:

- The hosted load-test tool was created, but the attempted live 1000-request health test against the production URL was not executed because the escalation request was rejected by the current usage limit.

Release judgment:

- The codebase now has the required SaaS control-plane pieces for PostgreSQL, per-user auth, tenant isolation, durable rate limiting, and queue-backed scans.
- At this historical checkpoint, the live deployment was not approved for unrestricted 1000-user external operation. The later section 24 records the Neon cutover and hosted health-load smoke; scan-heavy queue/provider load testing remains pending.

## 23. 2026-05-22 Vercel Queue Cleanup, Worker Cron Path, And Hosted Load Test

Implemented:

- Removed two stale Vercel deployments that had been stuck for roughly 23 hours:
  - `dpl_7jS12wawwZRQ5V4FduJZ7yTw8fnh`
  - `dpl_F3DzRPJsnwWyq9XxBUJjA8iAN8EM`
- Added protected worker endpoint `GET/POST /api/admin/run-worker`.
- Added `VCB_ALT_WORKER_TOKEN` and `VCB_ALT_WORKER_CRON_ENABLED`.
- Added Vercel Cron route for the worker endpoint with the Hobby-compatible daily schedule `0 0 * * *`.
- Kept worker cron disabled in production until PostgreSQL, scan queue, and worker token are configured.

Production deployment:

- Deployment `dpl_CvmPyyxFgHmAEP53wXWTEWu5hxtJ` succeeded and was aliased.
- Deployment `dpl_5kpzkW35wCt57BCzkwhrBNcdAsfL` succeeded and was aliased after changing cron from every 5 minutes to once daily for the Hobby plan.
- Production URL: `https://stockscreeningver10.vercel.app`.

Production environment check at this historical checkpoint:

- `VCB_ALT_DATABASE_URL` for managed PostgreSQL was not configured in Vercel Production yet.
- Production mode remained safe owner-trial mode:
  - `production_saas_ready=false`
  - `database_backend=sqlite`
  - `user_auth_enabled=false`
  - `rate_limit_backend=memory`
  - `scan_queue_enabled=false`
  - `worker_configured=false`
  - `worker_cron_enabled=false`

Worker endpoint smoke:

- `/api/admin/run-worker?limit=1` returned `disabled=true`, `processed=0`, `failed=0`.
- This confirms the route is deployed but cannot mutate queue state before production worker settings are enabled.

Hosted load test:

Command:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 1000 --concurrency 25 --timeout 15
```

Result:

- Requests: `1000`
- Concurrency: `25`
- Status `200`: `1000`
- Errors: `0`
- Elapsed: `54.626s`
- Throughput: `18.31 requests/s`
- Median latency: `1284.98ms`
- P95 latency: `2120.62ms`
- Max latency: `4259.43ms`

Final verification:

- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py`: passed, `lint ok (36 files)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py`: passed, `type hints ok (278 objects)`.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests`: passed, `44` tests.
- `C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall -q vcb_alt tests tools api`: passed.

Release judgment:

- Vercel queue/initialization issue is cleared.
- Latest safe build is deployed.
- Worker deployment path exists but remains disabled until managed PostgreSQL and worker token are configured.
- Hosted health load test passed for 1000 requests.
- Full public 1000-user operation is still blocked by missing managed PostgreSQL, production auth enablement, production tenant data migration, and real queue-backed scan load tests.

## 24. 2026-05-22 Neon PostgreSQL Cutover And SaaS Smoke

Implemented:

- Installed the Neon Marketplace integration after operator terms acceptance.
- Provisioned Neon resource `neon-cordovan-house` and connected it to the Vercel project.
- Mapped the Neon pooled `DATABASE_URL` into `VCB_ALT_DATABASE_URL`.
- Enabled production SaaS flags:
  - `VCB_ALT_USER_AUTH_ENABLED=true`
  - `VCB_ALT_USER_REGISTRATION_ENABLED=true`
  - `VCB_ALT_RATE_LIMIT_BACKEND=database`
  - `VCB_ALT_SCAN_QUEUE_ENABLED=true`
  - `VCB_ALT_WORKER_CRON_ENABLED=true`
  - `VCB_ALT_PRODUCTION_SAAS_MODE=true`
- Generated and configured matching `VCB_ALT_WORKER_TOKEN` and `CRON_SECRET`.
- Added `psycopg[binary]` as the production PostgreSQL runtime dependency.
- Removed temporary local env/token files containing secrets after verification.

Production deployment:

- Deployed PostgreSQL-backed production build.
- Final deployment: `dpl_J9FvSZUyTrpzHsLmDf9dtY9pEnES`.
- Production URL: `https://stockscreeningver10.vercel.app`.

Release-status verification:

- `production_saas_ready=true`
- `database_backend=postgresql`
- `user_auth_enabled=true`
- `rate_limit_backend=database`
- `scan_queue_enabled=true`
- `worker_configured=true`
- `worker_cron_enabled=true`

SaaS flow smoke:

- Registered a test user successfully.
- Added tenant-scoped watchlist: `PLTR`, `MSTR`, `VST`.
- Queued a tenant scan job successfully.
- Ran the protected worker endpoint successfully.
- Worker result: `processed=2`, `failed=0`.
- Latest smoke job result: `completed`, `count=3`, `failures=0`.

Hosted load test after PostgreSQL cutover:

Command:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 1000 --concurrency 25 --timeout 15
```

Result:

- Requests: `1000`
- Concurrency: `25`
- Status `200`: `1000`
- Errors: `0`
- Elapsed: `50.838s`
- Throughput: `19.67 requests/s`
- Median latency: `1200.6ms`
- P95 latency: `1917.36ms`
- Max latency: `4569.66ms`

Release judgment:

- Production now has the required PostgreSQL, per-user auth flag, tenant-scoped API path, database-backed rate limit setting, queue setting, worker token, and worker cron setting.
- The app passes SaaS control-plane smoke testing and health load smoke testing.
- Before fully public 1000-user marketing launch, run scan-heavy load tests, provider-budget tests, legal review, abuse monitoring, backup/restore drill, and support/incident workflows.

## 25. 2026-05-22 Expert Re-Read Optimization Verification

Implemented:

- Fixed PostgreSQL session datetime handling for psycopg `TIMESTAMPTZ` rows.
- Added atomic PostgreSQL queue claiming with `FOR UPDATE SKIP LOCKED`.
- Added PostgreSQL advisory locking to the durable database rate limiter.
- Persisted queued tenant scan results to `tenant_evaluations`.
- Hardened JSON/datetime decoding for PostgreSQL rows.
- Added TTL-bucketed process cache for Yahoo/Stooq market-data loaders.
- Updated planning/readiness docs to remove stale pre-Neon blockers.

Commands and results:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_saas_auth tests.test_db tests.test_stooq_provider -v
```

- Passed: `22` targeted regression tests.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py
C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests -v
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (36 files)`.
- Type check passed: `type hints ok (284 objects)`.
- Full tests passed: `50` tests.
- Compile/build passed for `vcb_alt`, `tests`, `tools`, and `api`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt benchmark --repeat 1000 --json
```

- Passed: `5000` evaluations, `33182.6 evals/s`, `0.0301 ms/evaluation`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt init-db --seed
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt scan --json
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt select --json
```

- Passed: local CLI smoke initialized the DB, scanned `7` tickers, and selected `PLTR`, `VST`, `MSTR`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m vcb_alt web --host 127.0.0.1 --port 8787
Invoke-RestMethod http://127.0.0.1:8787/api/health
Invoke-RestMethod http://127.0.0.1:8787/api/select?token=local-demo-token-123456
```

- Passed: local web server returned healthy status and selected `PLTR`, `VST`, `MSTR`.

Failed or not applicable:

- `npm run build` and `npm run release:preflight` failed because this repository has no `package.json`; Python `compileall` is the applicable build check.
- `python -m pip install .` failed in the sandbox because network access to build dependencies was blocked; escalation retry was rejected by the current usage limit. The local fallback Python environment also does not currently have `psycopg` installed, so local PostgreSQL mode was not exercised in this verification pass.
- In-app browser automation could not open the page because the browser runtime failed while writing internal assets. API-level local web verification passed.

Release judgment:

- The optimized code is safer for the current production SaaS control-plane path and remains suitable for controlled private beta.
- It is still not ready for unrestricted 1000-user public SaaS until scan-heavy hosted queue/provider load tests, auth hardening, monitoring, backup/restore, and legal review are complete.

## 26. 2026-05-22 Historical External-Release Gate Tooling Verification

Implemented:

- Added hosted SaaS queue load tool: `tools/host_queue_load_test.py`.
- Added local queue-backed 1000-user scan simulation tool: `tools/queue_load_test.py`.
- Added provider outage/budget simulation tool: `tools/provider_resilience_test.py`.
- Added operations health/alert tool: `tools/ops_health_report.py`.
- Added `AUTH_MFA_RBAC_PLAN.md`.
- Added `MONITORING_ALERTING_PLAN.md`.
- Added `NEON_BACKUP_RESTORE_DRILL.md`.
- Added `LEGAL_REVIEW_PACKET.md`.
- Added code-level RBAC helper `require_role(user, allowed_roles)`.
- Added per-user export/delete APIs, tenant admin users/audit/queue-status APIs, audit event storage, and stale job recovery.

Commands and results:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\provider_resilience_test.py
```

- Passed.
- Scan/select stayed structured under simulated provider outage/budget exhaustion.
- Failure count: `3`.
- Simulated provider calls: `6`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 100 --concurrency 10 --timeout 15
```

- Passed.
- Requests: `100`.
- HTTP `200`: `100`.
- Errors: `0`.
- P95 latency: `1514.91ms`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 3 --concurrency 2 --tickers PLTR,MSTR,VST --poll-seconds 5
```

- Passed as a queue-enqueue smoke.
- Registered/authenticated `3` users.
- Queued `3` scan jobs.
- Completed jobs: `0`.
- Reason: worker triggering was not enabled in this run because `VCB_ALT_WORKER_TOKEN` was not available to the local test runner.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app
```

- Health endpoint was reachable after network approval.
- Protected release/provider/readiness endpoints returned authentication-required without a shared access token env.
- Tool updated to support `--access-token-env VCB_ALT_WEB_ACCESS_TOKEN`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py
C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests -v
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (39 files)`.
- Type check passed: `type hints ok (285 objects)`.
- Full tests passed: `51` tests.
- Compile/build passed.

Additional 1000-user queue verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\queue_load_test.py --users 1000 --tickers 30 --worker-limit 100
```

- Users: `1000`.
- Queued jobs: `1000`.
- Completed jobs: `1000`.
- Failed jobs: `0`.
- Tenant evaluations: `30000`.
- Elapsed: `66.014s`.
- Throughput: `454.45 evals/s`.

Final verification after privacy/admin/queue recovery code:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\lint.py
C:\stable-diffusion-ui\installer_files\env\python.exe tools\typecheck.py
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests -v
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (40 files)`.
- Type check passed: `type hints ok (295 objects)`.
- Full tests passed: `52` tests.
- Compile/build passed.

Release judgment:

- Historical external-release gate tooling is now present and partially executed. This is not current launch approval.
- The app remains private-beta suitable.
- Unrestricted public 1000-user launch is still blocked until worker-triggered scan-heavy hosted load test, provider quota enforcement/alerts, OAuth/MFA/RBAC implementation, Neon staging restore drill, and external legal signoff are complete.

### 26.1 Production Cold-Start DDL Race Fix

Issue found during hosted post-deploy smoke:

- A 100-request `/api/health` hosted load run returned intermittent `500` responses.
- Vercel production logs showed concurrent serverless workers racing on PostgreSQL `audit_events_id_seq` creation while running SaaS schema initialization.

Fix implemented:

- `vcb_alt/tenant_store.py`: PostgreSQL SaaS schema initialization now uses `pg_advisory_xact_lock(...)`.
- `api/index.py`: `/api/health` now loads configuration only and skips database schema bootstrap.
- `tests/test_saas_auth.py`: added regression coverage proving PostgreSQL SaaS schema initialization takes the advisory lock.

Regression commands and results:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
```

- Lint passed: `lint ok (40 files)`.
- Type check passed: `type hints ok (295 objects)`.
- Full tests passed: `53` tests.
- Compile/build passed with `compileall`.
- Provider outage/budget simulation passed after the fix.
- Direct local 1000-user simulation passed: `30000` evaluations, `0` errors, tenant isolation passed, `24.898s`, `1204.91 evals/s`, p95 user flow `14.979ms`.
- Queue-backed local 1000-user simulation passed: `1000` completed jobs, `0` failed jobs, `30000` tenant evaluations, `68.675s`, `436.84 evals/s`.

Production redeploy and hosted smoke:

```powershell
npx.cmd vercel --prod --yes
```

- Deployed: `dpl_AkT17aQUWBzrMZy7dugaGuMyRDfR`.
- Production alias: `https://stockscreeningver10.vercel.app`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 1000 --concurrency 25 --timeout 20
```

- Passed.
- Requests: `1000`.
- HTTP `200`: `1000`.
- Errors: `0`.
- P95 latency: `1668.44ms`.

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 3 --concurrency 2 --tickers PLTR,MSTR,VST --poll-seconds 5
```

- Passed as a queue-enqueue hosted smoke.
- Registered/authenticated `3` users.
- Queued `3` scan jobs.
- Errors: `0`.
- Completed jobs: `0` because `--trigger-worker` was intentionally not used without exposing `VCB_ALT_WORKER_TOKEN` locally.

Frontend language regression:

```powershell
node --check data\app_check.js
node --check data\detail_check.js
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
```

- Restored corrupted Korean dashboard/detail translation strings.
- Dashboard JavaScript syntax passed.
- Detail-page JavaScript syntax passed.
- Final lint passed: `lint ok (40 files)`.
- Final type check passed: `type hints ok (295 objects)`.
- Final tests passed: `53` tests.

Final production deployment:

```powershell
npx.cmd vercel --prod --yes
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 200 --concurrency 20 --timeout 20
Invoke-WebRequest -UseBasicParsing https://stockscreeningver10.vercel.app/api/health
```

- Deployed: `dpl_7iWJ3a9cK3WDWCKwuy43SztLb5Vd`.
- Production alias: `https://stockscreeningver10.vercel.app`.
- Hosted health smoke passed: `200/200` HTTP `200`, `0` errors, p95 `1313.67ms`.
- Single health request returned `200 OK`.

## 27. 2026-05-24 Worker-Triggered Hosted Queue Completion Test

Setup:

- `VCB_ALT_WORKER_TOKEN` existed in Vercel Production but could not be pulled back as a plaintext value.
- Rotated `VCB_ALT_WORKER_TOKEN` to a new 64-character production token without printing it.
- Redeployed production after each worker-token rotation.
- Deleted the temporary pulled env file after use.

Worker-trigger completion smoke:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 10 --concurrency 2 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 90 --trigger-worker
```

- Deployed before test: `dpl_2bUZTZCSW5dneBuA6eiV1D5TADnq`.
- Users: `10`.
- Queued jobs: `10`.
- Completed jobs: `10`.
- Errors: `0`.
- Median latency: `2713.53ms`.
- P95 latency: `5019.1ms`.

Single-runner higher-load attempt:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 50 --concurrency 2 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 120 --trigger-worker
```

- Deployed before test: `dpl_9W6eR4SAjdhqVc2ERf6VrCBavpEK`.
- Users: `50`.
- Queued jobs: `24`.
- Completed jobs: `24`.
- Errors: `26`.
- Error cause: production rate limiter returned `Rate limit exceeded. Try again later.` from the single load-test source.
- Interpretation: worker-trigger completion path is proven, but one local runner cannot represent 1000 distinct public users without intentionally hitting the durable anti-abuse rate limit.

Post-test health/log check:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 100 --concurrency 10 --timeout 20
npx.cmd vercel logs --environment production --status-code 500 --since 15m --json
```

- Hosted health passed: `100/100` HTTP `200`, `0` errors, p95 `1021.65ms`.
- No new production `500` log entries were returned by the 15-minute 500-log query.

## 28. 2026-05-24 Full 1000-User Hosted Queue Completion Gate

Code hardening added before the final hosted run:

- Split durable rate-limit buckets by endpoint class:
  - unauthenticated auth/signup bucket
  - authenticated per-user/per-tenant bucket
  - protected worker bucket
  - default IP bucket for public/unknown API traffic
- Added hosted load-test support for `--worker-limit` and `--simulate-distributed-ips`.
- Added staged error labels to hosted load-test failures.
- Served dashboard/detail JavaScript now replaces the corrupted Korean i18n blocks before sending assets.
- `.env.example` now documents `VCB_ALT_AUTH_RATE_LIMIT_PER_MINUTE`, `VCB_ALT_USER_RATE_LIMIT_PER_MINUTE`, and `VCB_ALT_WORKER_RATE_LIMIT_PER_MINUTE`.

Regression verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
node --check data\served_app_check.js
node --check data\served_detail_check.js
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (40 files)`.
- Type check passed: `type hints ok (305 objects)`.
- Full tests passed: `55` tests.
- Served dashboard JavaScript syntax passed.
- Served detail JavaScript syntax passed.
- Compile/build passed.

Local queue-backed 1000-user verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\queue_load_test.py --users 1000 --tickers 30 --worker-limit 100
```

- Users: `1000`.
- Queued jobs: `1000`.
- Completed jobs: `1000`.
- Failed jobs: `0`.
- Tenant evaluations: `30000`.
- Elapsed: `48.79s`.
- Throughput: `614.88 evals/s`.
- Errors: `0`.

Hosted worker-triggered 1000-user completion:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load
```

- Deployed before test: `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`.
- Production alias: `https://stockscreeningver10.vercel.app`.
- Users: `1000`.
- Queued jobs: `1000`.
- Completed jobs: `1000`.
- Errors: `0`.
- Status counts: `completed=1000`.
- Tickers per user: `3`.
- Trigger worker: `true`.
- Worker limit: `100`.
- Concurrency: `20`.
- Elapsed: `243.152s`.
- Flows per second: `4.11`.
- Median latency: `4685.17ms`.
- P95 latency: `6049.49ms`.
- Max latency: `17311.08ms`.

Post-test production health/log check:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 300 --concurrency 20 --timeout 20
npx.cmd vercel logs --environment production --status-code 500 --since 15m --json
```

- Hosted health passed: `300/300` HTTP `200`, `0` errors, p95 `1572.27ms`.
- No new production `500` log entries were returned by the 15-minute 500-log query.
- Temporary worker token environment variable was cleared locally.
- Temporary pulled env file was not present.

## 29. 2026-05-24 SaaS Dashboard Scan Button Recovery

Issue reproduced from user report:

- The deployed dashboard could load, but clicking `Run scan` did not reliably show stock candidates for the user.

Historical root cause fixed in prior SaaS endpoint pass:

- Production SaaS mode blocked the legacy global `/api/watchlist`, `/api/scan`, and `/api/select` APIs by design.
- The dashboard button flow still used those legacy endpoints instead of tenant-scoped authenticated endpoints at that time.
- In browsers with stale generated demo credentials, the automatic session bootstrap could stop after both registration and login failed.

Fixes:

- Added tenant-scoped `POST /api/user/scan` and `POST /api/user/select`.
- Updated dashboard endpoint selection to use `/api/user/*` when per-user auth is enabled.
- Added browser-scoped automatic tenant registration/login, stale token cleanup, and fresh credential recovery.
- Historical legacy note: first-run starter watchlist seeding was added for browser tenants in the earlier watchlist-centered flow; current market-wide discovery keeps starter tickers behind an optional manual research helper.
- Changed scan response to include final selection so the UI can show candidates immediately after one `Run scan` click.
- Batched tenant evaluation persistence into one commit per scan.
- Added code comments documenting the interactive tenant scan path and batched persistence optimization.
- Added regression coverage for tenant scan/select API flow and dashboard JavaScript endpoint wiring.

Local verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
node --check data\served_app_check.js
node --check data\served_detail_check.js
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (40 files)`.
- Typecheck passed: `type hints ok (307 objects)`.
- Full tests passed: `55`.
- Served dashboard JavaScript syntax passed.
- Served detail JavaScript syntax passed.
- Compile/build passed.
- Local SaaS smoke passed: registered a user, added `7` tickers, scanned `7`, and selected `3` in `11ms`.

Production deployment:

```powershell
npx.cmd vercel --prod --yes
```

- Deployed: `dpl_EJwfpEvi9SnziMreYcbGAMeyVKGR`.
- Production alias: `https://stockscreeningver10.vercel.app`.

Production API smoke:

- Registered a fresh tenant user.
- Added watchlist: `PLTR MSTR VST AAPL GME RGTI SMMT`.
- `POST /api/user/scan`: passed, `7` tickers, `3` selected, `69ms`.
- `POST /api/user/select`: passed, selected `PLTR`, `VST`, `MSTR`.

Browser verification:

- Opened `https://stockscreeningver10.vercel.app/?token=...` in the in-app browser.
- Clicked `Run scan`.
- Dashboard displayed `Scan completed in 21 ms`.
- Candidate rows/cards rendered for `PLTR`, `VST`, `MSTR`, `GME`, `RGTI`, `SMMT`, and `AAPL`.
- Screenshot evidence:
  - `C:\Users\a\Downloads\stock_screening_ver1.0\scan-button-production-result.png`
  - `C:\Users\a\Downloads\stock_screening_ver1.0\scan-button-candidates-view.png`

Post-deploy hosted health smoke:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 100 --concurrency 10 --timeout 20
```

- Requests: `100`.
- Status `200`: `100`.
- Errors: `0`.
- Median latency: `601.59ms`.
- P95 latency: `955.29ms`.
- Requests/sec: `14.92`.

Release judgment for this issue:

- Historical scan-button note: the defect was fixed for the prior token-gated trial flow. Current external release remains blocked by the 2026-06-03 Alpaca live-scan status.
- Large hosted workloads should continue using the queue-backed scan path.
- Public paid/regulated launch still requires OAuth/email verification, admin MFA/RBAC rollout, external monitoring/alerts, provider outage/budget drills, Neon restore drill, and legal review.

## 30. 2026-05-24 Algorithm Review And Korean Localization

Scope:

- Reviewed the stock-selection algorithm from snapshot loading through archetype scoring, data coverage gating, and final portfolio selection.
- Added `ALGORITHM_REVIEW.md` so the selection logic can be explained without reading code.
- Tightened final selection tie-breaking so equal-score names prefer higher data coverage.
- Updated Korean dashboard/detail rendering so dynamic API strings are translated in Korean mode while ticker symbols and company/security names remain unchanged.

Algorithm finding:

- Core scoring was functional and already used more than chart data: archetype scores, fundamentals/earnings, catalysts/news, positioning, data coverage, optional intraday quote, and optional research enrichment all feed into the `StockSnapshot` and `EvaluationResult`.
- The final selection sort needed a precision improvement: equal-score candidates did not explicitly prefer stronger data coverage.

Fixes:

- `vcb_alt/portfolio.py`: added `_selection_sort_key()` with this order:
  - higher combined score
  - higher data coverage score
  - lower high-volatility penalty
  - higher suggested size
  - ticker as deterministic final tie-breaker
- `vcb_alt/web.py`: added Korean dynamic translation helpers for dashboard and detail pages.
- `tests/test_portfolio.py`: added equal-score data-coverage tie-break regression.
- `tests/test_web.py`: added Korean dynamic translation regression checks.

Verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
node --check data\served_app_check.js
node --check data\served_detail_check.js
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
```

- Lint passed: `lint ok (40 files)`.
- Typecheck passed: `type hints ok (308 objects)`.
- Tests passed: `56`.
- Dashboard JavaScript syntax passed.
- Detail JavaScript syntax passed.
- Compile/build passed.

Remaining:

- Production deployment/browser verification could not run in this pass because the approval system returned a usage-limit rejection for `npx vercel --prod --yes`.
- Local server startup for browser verification was also blocked by the same approval usage-limit rejection.
- Provider-specific Korean error messages can be expanded later, but the main dashboard/detail analysis copy is now localized.

## 31. 2026-06-03 Provider Resilience Guards

Scope:

- Added timeout/retry/quota-budget/circuit-breaker/fallback policy coverage for Alpaca, Finnhub, Yahoo, SEC, OpenAI, and the deterministic template summary provider.
- Added `/api/provider-health` for secret-safe provider policy/state visibility.
- Added durable `provider_alert_events` and `/api/admin/provider-alerts` for owner/admin provider incident review.
- Added deterministic fixtures for Alpaca `401`, Alpaca `429`, Alpaca timeout, Alpaca malformed JSON, Finnhub quota exhaustion, Yahoo outage, and OpenAI timeout/template fallback.
- Preserved production fail-closed behavior when `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true`: final candidate output cannot fall back to sample/demo output.

Commands attempted:

```powershell
python -m unittest tests.test_provider_resilience tests.test_web tests.test_saas_auth
py -3 -m unittest tests.test_provider_resilience tests.test_web tests.test_saas_auth
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest tests.test_provider_resilience tests.test_web tests.test_saas_auth
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.lint
C:\stable-diffusion-ui\installer_files\env\python.exe -m tools.typecheck
C:\stable-diffusion-ui\installer_files\env\python.exe -m unittest discover -s tests
C:\stable-diffusion-ui\installer_files\env\python.exe -m compileall vcb_alt tests tools api
git -c safe.directory=C:/Users/a/Downloads/stock_screening_ver1.0 diff --check
```

Results:

- `python -m unittest ...`: failed before test execution because `python` is not installed/discoverable on PATH in this shell.
- `py -3 -m unittest ...`: failed before test execution because the Windows Python launcher found no installed Python 3 runtime.
- Targeted provider/web/SaaS tests passed: `32` tests in `8.259s`.
- Lint passed: `lint ok (44 files)`.
- Typecheck passed: `type hints ok (415 objects)`.
- Full unit tests passed: `68` tests in `9.618s`.
- Compile/build smoke passed: `compileall vcb_alt tests tools api`.
- `git diff --check`: passed with no whitespace or conflict-marker errors.

Implemented fixes:

- Provider HTTP calls now pass through `vcb_alt.provider_resilience`.
- Alpaca snapshot malformed JSON raises `PROVIDER_MALFORMED_JSON` instead of silently continuing.
- Finnhub quota-style JSON payloads raise `PROVIDER_BUDGET_EXHAUSTED`.
- Yahoo provider outages surface as provider-aware `NotFoundError` messages.
- OpenAI timeout/failure falls back to deterministic `template-fallback`; OpenAI remains explanation-only.
- Worker scan failures record provider alert events when the exception is provider-originated.
- Alert metadata and provider health output avoid API key/secret exposure.

Remaining validation:

- Hosted provider outage/budget drills and hosted worker load tests still need to run after deployment with production provider keys and worker token.

Release judgment:

- This improves provider failure containment, but it does not make the service ready for unrestricted 1000-user SaaS.
- Current state remains owner/operator trial until live Alpaca diagnostics are ready, hosted worker/provider load tests pass again, external monitoring/alerting is connected, and legal/privacy review is complete.

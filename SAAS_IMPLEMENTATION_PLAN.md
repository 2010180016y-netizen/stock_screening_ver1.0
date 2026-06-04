# 1000-User SaaS Implementation Plan

Last updated: 2026-05-24

## 1. Goal

Design and execute a safe path from local owner/operator trial to a 1000-user SaaS product without pretending the current checkout can serve unrestricted public users directly.

## 2. Architecture Choice

Use a managed, boring SaaS stack:

- Web: Next.js/TypeScript
- API: FastAPI/Python
- Domain package: reusable Python scoring/validation module from `vcb_alt`
- DB: managed PostgreSQL
- Cache/rate limit: database-backed limiter now exists for the stdlib deployment; Redis/edge limits can be added later for higher scale
- Jobs: database-backed queue now exists for the stdlib deployment; Celery/RQ/managed queue can replace it later
- Storage: S3-compatible exports
- Observability: Sentry/OpenTelemetry/log metrics dashboards

Kubernetes, Kafka, and sharding are not phase-1 requirements for 1000 users.

## 3. Phase Plan

### Historical Checkpoint: Token-Protected Owner/Operator Trial

The codebase reached a Python stdlib web dashboard deployed on Vercel with token-gated access, EOD price/volume data, decision-first candidate cards, review/monitor grouping, provider metadata, and score detail modals. This is useful for controlled owner/operator feedback, but it is not a public 1000-user SaaS release.

The current gate is `OWNER_OPERATOR_TRIAL_SAFETY_LAYER`, which should improve product trust without pretending that full SaaS architecture or public-launch approval already exists.

Scope for this gate:

- Add external-review-safe labels for candidate status while preserving internal status codes for audit/debugging.
- Add scoring-version visibility to each evaluation result.
- Add provider status/capability reporting that does not expose secrets.
- Add starter legal/disclosure documents and link them from the UI.
- Add tests that lock these safety surfaces in place.

Still out of scope for this gate:

- Unrestricted signup/login.
- Billing.
- Per-user watchlists.
- Multi-tenant PostgreSQL.
- Investment-advice claims or automated trading.

### 2026-05-19 1000-User Boundary Progress

The repository now includes a disabled-by-default SaaS boundary:

- Per-user auth primitives using PBKDF2 password hashing and opaque session tokens.
- Tenant-scoped watchlist tables and API endpoints.
- PostgreSQL target migration in `migrations/postgres/001_saas_core.sql`.
- Basic in-process rate limiting for the stdlib server.
- Local 1000-user / 30,000-evaluation simulation in `tools/load_test.py`.

This is not yet the final unrestricted SaaS runtime. The next infrastructure gate must wire a managed PostgreSQL instance, Redis or edge rate limits, OAuth/email verification, admin MFA, backups, and deployed-host HTTP load tests.

### 2026-05-21 SaaS Readiness Implementation

Implemented:

- Optional PostgreSQL runtime adapter selected by `VCB_ALT_DATABASE_URL=postgresql://...`.
- Production SaaS boot guard through `VCB_ALT_PRODUCTION_SAAS_MODE=true`.
- Database-backed rate limiting through `VCB_ALT_RATE_LIMIT_BACKEND=database`.
- Tenant-scoped scan job queue through `VCB_ALT_SCAN_QUEUE_ENABLED=true`.
- Queue APIs: `POST /api/jobs/scan`, `GET /api/jobs`, `GET /api/jobs/{id}`.
- Worker command: `python -m vcb_alt worker run-once --limit 25`.
- Hosted load-test tool: `tools/host_load_test.py`.

Verified:

- Local SaaS smoke flow passed.
- Local 1000-user / 30,000-evaluation simulation passed with `0` errors and tenant isolation passed.

Production cutover update, 2026-05-22:

- Neon PostgreSQL is connected through Vercel Marketplace.
- `VCB_ALT_PRODUCTION_SAAS_MODE=true` reports production SaaS control-plane readiness.
- Production smoke passed for registration, tenant watchlist, scan queue, protected worker processing, and job status lookup.
- Hosted `/api/health` load smoke passed after cutover for `1000` requests at concurrency `25` with `0` errors.
- The worker endpoint and daily Vercel Cron route are wired with a protected worker token.
- Per-user export/delete APIs, tenant admin users/audit/queue-status APIs, audit event storage, and stale job recovery now exist.
- Local queue-backed 1000-user simulation passed with `1000` completed jobs, `30000` tenant evaluations, and `0` failures.
- PostgreSQL SaaS schema initialization now takes an advisory transaction lock so concurrent Vercel cold starts cannot race while creating tenant/audit tables.
- The Vercel `/api/health` path now avoids database DDL bootstrap and can serve as a fast uptime probe under traffic spikes.
- Endpoint-specific durable rate-limit buckets now separate auth/signup, authenticated tenant APIs, protected worker calls, and default public API traffic.
- Hosted worker-triggered production load completed `1000/1000` queued scan jobs with `0` errors on 2026-05-24.
- Dashboard `Run scan` now uses tenant-scoped `/api/user/scan` in SaaS mode, auto-recovers a browser tenant session, seeds a starter watchlist for first-run demo users, and returns final selection in the scan response so candidates appear after one button click.
- Production button-path smoke on 2026-05-24 scanned `7` tickers in `69ms` through the API and rendered candidates in the browser with `Scan completed in 21 ms`.

Still pending before unrestricted public SaaS:

- Periodic scan-heavy hosted queue load tests after provider/config changes.
- Provider outage and provider-budget tests for Yahoo/Finnhub/Alpaca/SEC paths.
- OAuth/email verification, admin MFA, RBAC, and abuse-prevention hardening.
- Centralized monitoring/alerts, queue-depth dashboards, Neon backup/restore drill, WAF/proxy hardening, and legal review.

### Phase 1: Domain Package Hardening

- Add scoring versioning. Status: implemented for evaluation results; next step is UI/API visibility.
- Add all seven current archetype fixture tests, including `G_TECHNICAL_MOMENTUM`.
- Remove any CLI/DB assumptions from scoring.
- Add benchmark tests. Status: local benchmark exists; deployed `/api/health` load smoke passed, scan-heavy queue load test remains pending.
- Add neutral product language option for SaaS UI. Status: implemented for the current dashboard as `public_label`.

### Phase 2: SaaS Core

- Create API service skeleton. Status: partial stdlib API boundary exists for auth and tenant watchlists.
- Add auth provider integration. Status: local auth primitives exist; OAuth/email verification still pending.
- Add PostgreSQL migration system. Status: target SQL migration exists and includes tenant, session, watchlist, evaluation, rate-limit, and scan-job tables.
- Add tenants/users/watchlists/evaluations/jobs/audit_events schema. Status: tenants/users/sessions/watchlists/evaluations/jobs exist; audit_events pending.
- Add object-level authorization tests. Status: tenant watchlist isolation tests exist.
- Add API response envelope and idempotency keys.

### Phase 3: Jobs And Providers

- Add worker service. Status: `worker run-once`, protected worker endpoint, and daily Vercel Cron route exist; worker observability/retry policies remain pending.
- Add job state machine. Status: queued/running/completed/failed states exist.
- Add provider adapter interface.
- Add caching and freshness labels.
- Add provider budget enforcement.
- Add retries, circuit breakers, dead-letter queue.

### Phase 4: Web And Admin UX

- Build signup/login/onboarding.
- Build watchlist/results/settings/export/delete screens.
- Build admin users/jobs/provider-status/audit screens.
- Add empty/loading/error/success states.
- Add non-developer usability tests.

### Phase 5: Production Readiness

- Load test 1000 users and 30,000 daily evaluations.
- Run tenant-isolation security tests.
- Run backup/restore drill.
- Complete legal/privacy review.
- Create support and incident runbooks.
- Launch capped beta.

## 4. Code Changes Made In This Pass

- Added architecture, data model, API, security, operations, migration, and load-test docs.
- Added `vcb_alt.saas_readiness` with explicit P0/P1 blockers.
- Added `python -m vcb_alt saas-readiness`.
- Added tests to prevent accidental 1000-user readiness claims.

## 5. Immediate Next Engineering Tasks

1. Surface `SCORING_VERSION` in the UI and tests.
2. Add SaaS-safe display labels that avoid direct trade-action wording.
3. Add provider status/capability API for operator trust and future adapter boundaries.
4. Add starter `TERMS.md`, `PRIVACY.md`, and `RISK_DISCLOSURE.md`.
5. Run scan-heavy hosted queue load tests against production-like PostgreSQL.
6. Add provider quota dashboards, circuit breakers, and outage drills.
7. Add OAuth/email verification, admin MFA, and RBAC.
8. Add centralized monitoring, backup/restore drill evidence, and legal-reviewed launch docs.

## 6. Risk Register

- Legal risk: scoring output may be interpreted as advice. Mitigation: legal review and SaaS-safe wording.
- Data isolation risk: current DB has no tenants. Mitigation: new PostgreSQL model and authorization tests.
- Provider cost risk: 1000 users can multiply API calls. Mitigation: shared market data cache and budgets.
- Operational risk: queue backlog and provider outages. Mitigation: workers, DLQ, dashboards, alerts.
- Product trust risk: sample data is not useful for real users. Mitigation: clear freshness labels and real provider plan.

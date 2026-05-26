# Release Decision

Decision date: 2026-05-18 KST

Latest update: 2026-05-21 KST

Latest deployment update: 2026-05-24 KST

## 1. Final State

READY_FOR_PUBLIC_BETA.

The product now runs as a local CLI, local token-protected web dashboard, and deployed Vercel private-beta site at `https://stockscreeningver10.vercel.app`. It can initialize SQLite, manage a watchlist, fetch automatic end-of-day market data, compute market-derived precision metrics, scan, select candidates, show operations/failures, and run in a browser.

2026-05-19 update: the public-beta safety layer now adds SaaS-safe review labels, scoring-version visibility, provider-status reporting, and starter Terms/Privacy/Risk documents. These reduce launch ambiguity but do not remove the need for real auth, durable storage, legal review, or load testing.

Second 2026-05-19 update: per-user auth primitives, tenant-scoped watchlist APIs, a PostgreSQL target migration, basic in-process rate limiting, and a local 1000-user load simulation now exist. This reduces several engineering blockers but does not yet make the deployed demo an unrestricted 1000-user public SaaS because live PostgreSQL, Redis/edge rate limits, OAuth/MFA, and deployed-host load tests are still pending.

2026-05-20 update: the product now has a safe full-data architecture for Alpaca near-real-time quotes, Finnhub fundamentals/news/short/options/analyst enrichment, SEC filing metadata, and AI summaries. These layers are disabled or template-only by default until the operator configures real credentials.

Second 2026-05-20 update: the current build is finalized as an owner pre-user usage version. `/api/release-status` reports `release_channel=operator_trial`, and `OPERATOR_TRIAL_GUIDE.md` defines what the operator can test before inviting users.

2026-05-21 update: Finnhub production enrichment is verified and should remain enabled for the owner trial. Alpaca variables are present but Alpaca returns HTTP 401, so the practical owner-trial deployment should keep `VCB_ALT_INTRADAY_DATA_PROVIDER=none` until the credential pair is corrected. The detail API now avoids duplicate snapshot/provider calls and HTTPS token cookies are hardened with `Secure`.

Final 2026-05-21 operator-trial deployment: production deployment `dpl_HTTYjmssPW8z61JxhS74ee1qV2t2` is live at `https://stockscreeningver10.vercel.app/?token=vcb-beta-20260518-4f6b9c2d8a7e4b1f9a0c3d2e5f6a7b8c`. Smoke verification passed with `release_channel=operator_trial`, `user_trial_ready=true`, `public_launch_ready=false`, `research_provider=finnhub`, `research_ready=true`, `intraday_provider=none`, and `intraday_ready=false`. PLTR detail analysis returned `yahoo+finnhub`, data coverage `100/100`, score `55`, `AI Pick & Shovel`, `Technology / Software - Infrastructure`, and a five-year chart with `1256` daily points.

SaaS readiness implementation update: PostgreSQL adapter hooks, production SaaS boot guard, database-backed rate limiting, tenant-scoped scan job APIs, and a queue worker command now exist. Local 1000-user / 30,000-evaluation simulation passed with `0` errors and tenant isolation passed. The later 2026-05-22 Neon cutover configured managed PostgreSQL in Vercel Production and completed hosted `/api/health` load smoke; scan-heavy hosted queue/provider load testing remains pending.

2026-05-22 update: stale Vercel deployments stuck in `Initializing` and `Queued` were removed, the latest safe build was redeployed, and `https://stockscreeningver10.vercel.app` is healthy. A protected worker endpoint and daily Hobby-compatible Vercel Cron route now exist, but production worker execution remains disabled until PostgreSQL, scan queue, and worker token are configured. Hosted health load test passed with `1000/1000` HTTP 200 responses and `0` errors.

Second 2026-05-22 update: Neon PostgreSQL is now connected through Vercel Marketplace and production SaaS mode reports `production_saas_ready=true`. The deployed app is using PostgreSQL, per-user auth is enabled, database rate limiting is configured, scan queue is enabled, worker token is configured, and worker cron is enabled. A production SaaS smoke test passed for registration, tenant watchlist, scan queue, protected worker processing, and job status lookup. Hosted health load test passed after cutover with `1000/1000` HTTP 200 responses and `0` errors.

Third 2026-05-22 update: an expert re-read fixed PostgreSQL session datetime handling, atomic PostgreSQL queue claiming, database rate-limit concurrency, tenant evaluation persistence for queued scans, PostgreSQL JSON/datetime decoding, and market-data process cache TTL behavior. Local verification passed lint, typecheck, `50` tests, compile/build, benchmark, CLI smoke, and local web API smoke. Local dependency installation could not be completed because sandbox network escalation was rejected, so local PostgreSQL mode was not exercised in this pass.

Fourth 2026-05-22 update: public-launch gate tooling now exists for hosted queue load testing, provider outage/budget simulation, operations health reporting, OAuth/MFA/RBAC planning, monitoring/alerting, Neon restore drill, and legal review handoff. A small hosted queue smoke registered `3` users and queued `3` scan jobs; completion could not be verified because the local test runner did not have `VCB_ALT_WORKER_TOKEN` for manual worker triggering. Final verification passed lint, typecheck, `51` tests, and compile/build.

Fifth 2026-05-22 update: the code now includes per-user export/delete APIs, tenant admin users/audit/queue-status APIs, audit event storage, stale running job recovery, and a local queue-backed 1000-user simulation. Local queue simulation completed `1000` jobs and stored `30000` tenant evaluations with `0` failures. Final verification passed lint, typecheck, `52` tests, and compile/build.

2026-05-24 1000-user operating update: endpoint-specific durable rate-limit buckets now separate auth/signup, authenticated tenant APIs, protected worker calls, and default public API traffic. Served dashboard/detail JavaScript replaces corrupted Korean i18n blocks before response. Final regression passed lint, typecheck, `55` tests, served JS syntax checks, and compile/build. Local queue-backed load completed `1000` jobs / `30000` evaluations with `0` failures. Hosted worker-triggered production load completed `1000/1000` queued scan jobs with `0` errors on deployment `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`; post-run health returned `300/300` HTTP `200` and no new production `500` logs.

2026-05-24 dashboard scan-button update: the deployed dashboard now routes `Run scan` through tenant-scoped `/api/user/scan` in SaaS mode, auto-recovers browser demo sessions, seeds a starter watchlist, and returns final selection in the scan response. Production API smoke scanned `7` tickers in `69ms` and selected `PLTR`, `VST`, `MSTR`; browser verification showed `Scan completed in 21 ms` and rendered candidate results on deployment `dpl_EJwfpEvi9SnziMreYcbGAMeyVKGR`.

It is suitable for a free/public beta of the decision-support SaaS with clear risk disclosure, no payment collection, no automated trading, and operator monitoring enabled. It must not be marketed as investment advice or a paid advisory product until legal review, support operations, and provider licensing are finalized.

## 2. Resolved P0/P1 Items

- P0 resolved: runnable package, CLI, DB init, validation, tests, and docs exist.
- P1 resolved: local web dashboard exists and was browser-verified.
- P1 resolved: automatic `yahoo` market-data provider fetches and caches EOD chart data.
- P1 resolved: optional `stooq` provider fails clearly when API key/captcha is required.
- P1 resolved: technical momentum scoring produces candidates from price/volume-only data.
- P1 resolved: public web mode requires a 16+ character token.
- P1 resolved: unauthorized public API calls return `401`.
- P1 resolved: Dockerfile, Render config, and public deployment guide exist.
- P1 resolved: Vercel serverless adapter exists and production deployment was verified.
- P1 resolved: deployed Vercel API rejects unauthenticated protected requests with `401`.
- P1 resolved: deployed Vercel selection API returned live Yahoo-based candidates with zero provider failures.
- P1 resolved: public UI now uses neutral review labels instead of direct trade-action wording.
- P1 resolved: evaluation results expose `scoring_version` and `public_label`.
- P1 resolved: provider status/capability endpoint exists without exposing secrets.
- P1 resolved: optional full-data enrichment structure exists for intraday quote, fundamentals, earnings, news, filings, analyst trends, short interest, options, and AI explanation.
- P1 partially resolved: Terms, Privacy, and Risk Disclosure drafts exist for legal review.
- P1 partially resolved: per-user auth/session APIs exist and are disabled by default.
- P1 partially resolved: tenant-scoped watchlist storage and tests exist.
- P1 resolved for control-plane smoke: PostgreSQL is connected in production.
- P1 resolved for control-plane smoke: database-backed rate limiting is configured in production.
- P1 resolved for control-plane smoke: tenant-scoped scan queue APIs, worker command, protected worker endpoint, and Vercel Cron route are configured in production.
- P1 resolved for control-plane correctness: PostgreSQL session datetime handling, atomic queue claim path, durable rate-limit bucket locking, and queued-scan tenant evaluation persistence are implemented and regression-tested locally.
- P1 partially resolved: local 1000-user / 30,000-evaluation load simulation passed.
- P1 partially resolved: hosted `/api/health` load smoke test passed for 1000 requests.
- P1 partially resolved: hosted queue-enqueue smoke test passed for 3 users and 3 queued jobs.
- P1 partially resolved: provider outage/budget simulation tool passed locally.
- P1 partially resolved: monitoring/alerting, OAuth/MFA/RBAC, Neon restore, and legal review packets now exist.
- P1 partially resolved: code-level RBAC helper exists, but admin/export/delete endpoints still need full role enforcement and MFA step-up.
- P1 resolved locally: queue-backed 1000-user simulation passed with 1000 completed jobs, 30000 tenant evaluations, and 0 failures.
- P1 resolved locally: per-user export/delete and tenant admin users/audit/queue-status APIs exist and are regression-tested.
- P1 resolved for deploy stability: PostgreSQL SaaS schema initialization is serialized with an advisory transaction lock after production logs showed an `audit_events_id_seq` cold-start race.
- P1 resolved for uptime probes: `/api/health` no longer runs database DDL bootstrap.
- P1 resolved for hosted health smoke after redeploy: `1000/1000` production health requests returned `200` with `0` errors at concurrency `25`.
- P1 partially resolved for hosted queue smoke after redeploy: `3` production users registered/authenticated and queued `3` scan jobs with `0` errors.
- P1 resolved for final deploy health smoke: final production deploy `dpl_7iWJ3a9cK3WDWCKwuy43SztLb5Vd` returned `200/200` health responses with `0` errors at concurrency `20`.
- P1 resolved for worker-trigger path: hosted queue completion smoke completed `10/10` jobs with `0` errors after rotating the production worker token.
- P1 blocker refined: single-runner hosted queue load reached `24/50` completed jobs before the production durable rate limiter correctly blocked the remaining requests.
- P1 resolved for 1000-user operating gate: hosted worker-triggered production load completed `1000/1000` scan jobs with `0` errors.
- P1 resolved for rate-limit scalability: auth/signup, authenticated tenant API, worker, and default public API traffic now use separate durable buckets.
- P1 resolved for deployed UI stability: served dashboard/detail JavaScript passes syntax checks after Korean i18n replacement.
- P1 resolved for deployed dashboard use: the `Run scan` button now uses tenant-scoped scan/select APIs in SaaS mode and renders candidates after one click.

## 3. Remaining P1/P2/P3 Items

P1:

- Add email verification/OAuth, admin MFA, and richer RBAC before paid launch or broad marketing.
- Add external monitoring/alerts for database rate limiting, queue depth, worker failures, and provider errors.
- Run backup/restore drill on Neon.
- Replace starter Terms, Privacy, and Risk Disclosure drafts with legal-reviewed launch documents.
- Add WAF/proxy hardening and centralized observability before paid or regulated use.

P2:

- Add licensed/contracted market-data provider support for production use.
- Add provider live contract tests in CI/staging.
- Add backup/restore automation and Neon restore-drill evidence.
- Add periodic deployed-host scan-heavy queue load tests to catch regressions after provider/config changes.
- Add optional PostgreSQL integration tests gated by `VCB_ALT_TEST_DATABASE_URL`.

P3:

- Add richer charts and ranking explanations.
- Add scheduled scans and email/slack alerts.
- Add per-sector universe import.

## 4. Publicly Usable Scope

Allowed now:

- Controlled private beta.
- Token-protected deployed demo site for a small trusted audience.
- Free/public beta for up to the tested 1000-user queue workload.
- Decision-support screening with no trade execution.

Not allowed yet:

- Open signup without abuse monitoring, support coverage, and email verification.
- Paid public investment product.
- Claims of financial advice or guaranteed returns.

## 5. Features That Must Not Be Publicly Exposed

- Automatic trading or broker integration.
- Multi-user data storage without tenant isolation.
- Admin/operations endpoints without real auth/RBAC.
- Any page that markets outputs as investment advice.
- Any collection of sensitive personal/payment data.

## 6. Next 7 Days

- Decide production data-provider terms and licensing.
- Add a real auth provider with email verification/OAuth, or keep the demo strictly token-gated.
- Add request IDs and structured access logs.
- Add scan-heavy deployed load test and provider outage drill.
- Send Terms/Privacy/Risk disclaimer drafts for legal review and apply counsel feedback.

## 7. Next 30 Days

- Add migration drift checks and backup/restore drill for Neon.
- Add deployed user/tenant cross-access tests and per-user export/delete flows.
- Add provider retry/backoff, stale-running job recovery, and dead-letter handling.
- Add dashboards/alerts for provider failures, scan latency, and 5xx errors.
- Run staging load/security tests before broader beta.

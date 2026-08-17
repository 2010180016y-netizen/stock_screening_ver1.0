# VCB-Alt

Local-first US stock screening decision-support CLI and token-protected web dashboard.

VCB-Alt scans a configured US-equity market universe, prefilters live/near-live movers, enriches the strongest candidates, scores them across seven stock archetypes, and surfaces a small decision-support candidate set through deterministic scoring and portfolio constraints. User watchlists remain as a manual research aid, not the primary discovery engine. The app does not place trades and does not call external market-data providers unless explicitly enabled.

## Major Features

- Local SQLite setup with `init-db`
- Market-universe scan mode for all-market discovery
- Watchlist add/list/remove/seed commands for manual research lists
- Single ticker evaluation with validation and risk warnings
- Market scan with empty/success/error-safe states
- Manual CSV data provider for operator-supplied real snapshots
- Yahoo chart and optional Stooq end-of-day market-data providers with local cache
- Optional Alpaca active-asset universe and near-real-time multi-symbol snapshot prefilter with a short TTL cache
- Technical Momentum scoring for automatic market data with a data-quality gate that blocks chart-only final selections
- Optional `data/enrichment.csv` overlay for fundamentals, catalysts, short/options, insider, float, and related context
- Optional Finnhub research-data provider for fundamentals, earnings surprise, news catalysts, analyst trends, short interest, options open interest, and insider transactions
- Optional SEC submissions metadata layer for recent filing context
- Explanation summary layer: deterministic template summary by default, with optional OpenAI-generated explanation summaries when explicitly configured
- Portfolio candidate selection with position, archetype, and high-volatility constraints
- Local web dashboard with market scan table, final selection, manual watchlist, and operations status
- Decision-first owner-trial UI with SaaS-safe review labels, scoring-version visibility, and legal/disclosure links
- Click-through ticker analysis pages with five-year chart, sector/industry, current status, and selection rationale
- Responsive dashboard and ticker detail pages for desktop, mobile, and browser zoom
- Korean/English language toggle for the public dashboard and ticker analysis page
- Provider status API that reports market-data capabilities without exposing secrets
- Disabled-by-default per-user auth boundary with tenant-scoped watchlist APIs for SaaS migration testing
- Optional PostgreSQL adapter and target schema under `migrations/postgres`
- Database-backed rate limiting and queue-backed scan job APIs for SaaS migration testing
- Local and hosted load-test tools for future SaaS readiness verification
- Optional public web mode with a deployment access token
- Throughput benchmark command
- Operator logs, failed-job history, export, and destructive delete confirmation
- Secret-redacted logging
- Offline deterministic sample data for first-run private beta testing
- Python stdlib-only runtime; `psycopg[binary]` is an optional extra needed only for PostgreSQL mode

## Tech Stack

- Python 3.11+
- SQLite for local development
- PostgreSQL/Neon for production SaaS mode
- `psycopg[binary]` for PostgreSQL connectivity (optional extra: `pip install ".[postgres]"`)
- `argparse`, `sqlite3`, `unittest`, and other Python standard-library modules

## Local Setup

```powershell
# Optional
Copy-Item .env.example .env

# Install the package. Local SQLite development needs no third-party dependencies.
python -m pip install .

# Only if VCB_ALT_DATABASE_URL points at PostgreSQL (this is how the hosted deployment runs):
python -m pip install ".[postgres]"

# Initialize local database and seed sample tickers.
python -m vcb_alt init-db --seed

# Verify configuration.
python -m vcb_alt doctor
```

Verified on this Windows machine with Python 3.11.9 on PATH (2026-08-17). Earlier
revisions of this document pointed at an interpreter under `C:\stable-diffusion-ui\`;
that path no longer exists, so use `python` directly.

## Environment Variables

Required for MVP: none.

Suggested local/operator variables:

```dotenv
VCB_ALT_DATABASE_URL=sqlite:///./data/vcb_alt.db
VCB_ALT_LOG_LEVEL=INFO
VCB_ALT_TIMEZONE=Asia/Seoul
VCB_ALT_DATA_PROVIDER=sample
VCB_ALT_EXTERNAL_API_ENABLED=false
VCB_ALT_MARKET_DATA_TIMEOUT_SECONDS=10
VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS=12
VCB_ALT_PROVIDER_RETRY_ATTEMPTS=2
VCB_ALT_PROVIDER_RETRY_BACKOFF_SECONDS=0.05
VCB_ALT_PROVIDER_CIRCUIT_FAILURE_THRESHOLD=3
VCB_ALT_PROVIDER_CIRCUIT_RESET_SECONDS=300
VCB_ALT_SCAN_MODE=market_universe
VCB_ALT_MARKET_UNIVERSE_PROVIDER=auto
VCB_ALT_MARKET_UNIVERSE_MAX_SYMBOLS=5000
VCB_ALT_MARKET_PREFILTER_LIMIT=30
VCB_ALT_MARKET_SNAPSHOT_BATCH_SIZE=100
VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=false
VCB_ALT_PUBLIC_WEB_ENABLED=false
VCB_ALT_WEB_ACCESS_TOKEN=replace-with-at-least-16-random-characters
VCB_ALT_AUTO_SEED_SAMPLE=true
VCB_ALT_ALLOW_QUERY_TOKEN_AUTH=true
VCB_ALT_TRUSTED_PROXY_HEADERS=false
VCB_ALT_MAX_JSON_BODY_BYTES=65536
VCB_ALT_GLOBAL_OPERATOR_EMAILS=
```

`sample` is the safe offline default. `manual` reads `data/snapshots.csv`. `yahoo` fetches end-of-day chart data and requires `VCB_ALT_EXTERNAL_API_ENABLED=true`. `stooq` is also supported, but some Stooq downloads require an API key/captcha flow.
`VCB_ALT_SCAN_MODE=market_universe` is the intended product mode. It scans the configured universe instead of only user-entered watchlist symbols. Set `VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA=true` in production so the app fails closed when live Alpaca snapshots are unavailable.
`VCB_ALT_AUTO_SEED_SAMPLE=true` only seeds the legacy/local watchlist flow. It is ignored for `market_universe` and production SaaS core flows; starter tickers appear only as an optional manual research helper.
Provider-heavy paths use timeout, retry, quota-budget, and circuit-breaker guards. Operators can inspect `/api/provider-health` and `/api/admin/provider-alerts` without exposing API keys.
For production SaaS, set `VCB_ALT_ALLOW_QUERY_TOKEN_AUTH=false`; production mode forces query-token auth off so `?token=` and `?worker_token=` cannot become public access paths. Set `VCB_ALT_TRUSTED_PROXY_HEADERS=true` only behind a trusted proxy that sanitizes `X-Forwarded-For`. Use `VCB_ALT_GLOBAL_OPERATOR_EMAILS` or `operator`/`global_operator` roles for cross-tenant provider alert visibility.

## Usage

```powershell
python -m vcb_alt watchlist list
python -m vcb_alt watchlist add PLTR MSTR
python -m vcb_alt evaluate PLTR
python -m vcb_alt scan
python -m vcb_alt select
python -m vcb_alt benchmark --repeat 1000
python tools\load_test.py --users 1000 --tickers 30
python tools\queue_load_test.py --users 1000 --tickers 30 --worker-limit 100
python -m vcb_alt web --host 127.0.0.1 --port 8765
python -m vcb_alt admin logs
python -m vcb_alt admin failures
```

`python -m vcb_alt scan` follows `VCB_ALT_SCAN_MODE`. Use `python -m vcb_alt scan --watchlist` only for the legacy/manual ticker list flow.

Then open:

```text
http://127.0.0.1:8765
```

## Use Market Data

For automatic end-of-day market data:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
```

Then run:

```powershell
python -m vcb_alt evaluate AAPL
python -m vcb_alt scan
python -m vcb_alt select
```

The automatic market-data provider calculates price/volume-derived fields such as 12-week return, 52-week drawdown, moving-average distances, trend template score, surge score, and relative strength versus SPY when available. Fundamentals, catalysts, short interest, and options metrics are not available from this provider by itself.

Price/volume-only scans are now blocked from final selection by the data-quality gate. To let automatic market data participate in final selection, add operator-verified enrichment:

1. Copy `data/enrichment.example.csv` to `data/enrichment.csv`.
2. Fill one row per ticker with trusted fundamentals, catalyst, short/options, insider, float, and related context.
3. Keep automatic market data enabled:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
```

4. Run:

```powershell
python -m vcb_alt scan
python -m vcb_alt select
```

The selection engine requires at least `60/100` data coverage before a ticker can become a final candidate. The four coverage groups are market price/volume, fundamentals/earnings, catalyst/news, and positioning.

For API-backed research enrichment:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_RESEARCH_DATA_PROVIDER=finnhub
VCB_ALT_FINNHUB_API_KEY=replace-with-your-key
```

`finnhub` attempts to enrich each market snapshot with fundamentals, earnings surprise, recent company news, analyst rating/revision trends, insider transaction activity, short interest, and option-chain open interest. Use `finnhub_csv` when you want Finnhub data first and `data/enrichment.csv` as an operator-reviewed override. Missing or failed research calls do not crash the scan; they leave the data coverage low so final selection remains blocked.

For near-real-time quote context:

```dotenv
VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca
VCB_ALT_ALPACA_API_KEY=replace-with-your-key
VCB_ALT_ALPACA_API_SECRET=replace-with-your-secret
VCB_ALT_ALPACA_DATA_FEED=iex
VCB_ALT_INTRADAY_CACHE_TTL_SECONDS=60
```

For SEC filing context and explanation summaries:

```dotenv
VCB_ALT_SEC_COMPANY_FACTS_ENABLED=true
VCB_ALT_SEC_USER_AGENT=vcb-alt-stock-screener your-email@example.com
VCB_ALT_AI_SUMMARY_PROVIDER=template
# Optional OpenAI explanation-summary mode:
VCB_ALT_AI_SUMMARY_PROVIDER=openai
VCB_ALT_OPENAI_API_KEY=replace-with-your-key
VCB_ALT_OPENAI_MODEL=gpt-4.1-mini
```

Stock selection is performed by deterministic scoring and portfolio constraints. The summary layer never selects stocks; it only explains the score, data coverage, chart, sector, filings, news, options, and analyst fields already present in the API response. When OpenAI is disabled, the UI and API label this as `template summary`. `openai` mode calls the OpenAI Responses API only when a key is configured and falls back to the local template summary if the call fails.

For operator-supplied full snapshots:

1. Copy `data/snapshots.example.csv` to `data/snapshots.csv`.
2. Fill one row per ticker with your trusted data source.
3. Set `.env`:

```dotenv
VCB_ALT_DATA_PROVIDER=manual
```

4. Run:

```powershell
python -m vcb_alt scan
python -m vcb_alt select
```

`select` applies the current portfolio rules: up to 3 positions, default total suggested exposure cap of 75%, no duplicate primary archetype, and at most one high-volatility archetype.

JSON output:

```powershell
python -m vcb_alt evaluate PLTR --json
```

Delete all local app data:

```powershell
python -m vcb_alt admin delete-data --confirm DELETE_LOCAL_DATA
```

## Test

```powershell
python -m unittest discover -s tests -v
python tools\typecheck.py
python tools\lint.py
python -m compileall vcb_alt tests tools api
```

## Build

This CLI has no frontend bundle. Build verification is bytecode compilation:

```powershell
python -m compileall vcb_alt tests tools api
```

## Deployment

Local/private deployment:

1. Copy the folder to the operator machine.
2. Copy `.env.example` to `.env`.
3. Run dependency install.
4. Run `python -m vcb_alt init-db --seed`.
5. Run `python -m vcb_alt self-test`.

Token-protected operator-trial deployment is supported behind a deployment token. See `PUBLIC_DEPLOYMENT.md`, `DEPLOYMENT.md`, and `OPERATIONS.md`.

Future 1000-user SaaS mode is guarded by `VCB_ALT_PRODUCTION_SAAS_MODE=true`. The app refuses to start that mode unless PostgreSQL, per-user auth, database-backed rate limiting, and scan queue are enabled together. This guard does not approve the current deployment for unrestricted 1000-user external release. Current status is `public_launch_ready=false` and `NOT_READY_FOR_1000_USER_SAAS` until Alpaca diagnostics, live market-universe scan verification, auth hardening, monitoring, backup/restore, legal review, and hosted scan-heavy load testing all pass.

Historical hosted queue-load verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load
```

Historical result: `1000` queued jobs, `1000` completed jobs, `0` errors on production deployment `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`. This is not current public-launch approval because the present live market-universe scan is blocked by Alpaca credential `HTTP 401`.

Ticker detail pages:

```text
http://127.0.0.1:8765/ticker/AAPL
```

The detail page shows a five-year daily price/volume chart when the provider supports history data. Current no-key providers are labeled as end-of-day/delayed data, not tick-by-tick real-time data.

Legal and risk draft documents:

- [Terms draft](docs/TERMS.md)
- [Privacy notice draft](docs/PRIVACY.md)
- [Risk disclosure draft](docs/RISK_DISCLOSURE.md)

These drafts are operational placeholders and require legal review before public, paid, or unrestricted external release.

## Repository Layout

Reference documentation lives in [docs/](docs). The repository root keeps only the five
files needed to start working: this README, [CHANGELOG.md](CHANGELOG.md),
[SETUP.md](SETUP.md), [TESTING.md](TESTING.md), and
[RELEASE_DECISION.md](RELEASE_DECISION.md) — the authoritative statement of what is and
is not ready to ship. Implementation handoff notes are in [codex_handoff/](codex_handoff).

## Research And Planning

- [Deep system research](docs/research.md): current architecture, runtime flow, provider behavior, scoring, web/API, operations, risks, and scaling constraints.
- [Operator trial guide](docs/OPERATOR_TRIAL_GUIDE.md): owner pre-user usage URL, workflow checklist, provider mode, and public-launch blockers.
- [Provider keys setup](docs/PROVIDER_KEYS_SETUP.md): safe Vercel/local setup for Alpaca, Finnhub, SEC, and OpenAI keys.
- [OAuth/MFA/RBAC plan](docs/AUTH_MFA_RBAC_PLAN.md): auth hardening and role matrix before unrestricted external release.
- [Monitoring and alerting plan](docs/MONITORING_ALERTING_PLAN.md): operational dashboards, alerts, and health-report tooling.
- [Neon backup/restore drill](docs/NEON_BACKUP_RESTORE_DRILL.md): staging-first recovery drill and evidence checklist.
- [Legal review packet](docs/LEGAL_REVIEW_PACKET.md): counsel-facing launch review checklist and official reference links.
- [Feature 00 implementation plan](docs/plan.md): input-based/keyset paging plan for list APIs without SQL `OFFSET`.
- [QA report](docs/QA_REPORT.md): latest executed verification results.
- [Release decision](RELEASE_DECISION.md): current owner-trial readiness and remaining public-SaaS blockers.
- [SaaS implementation plan](docs/SAAS_IMPLEMENTATION_PLAN.md): future SaaS hardening path.
- [PostgreSQL migration](migrations/postgres/001_saas_core.sql): target SaaS tenant/user/session/watchlist/evaluation/rate-limit/job schema.

## Known Limitations

- Yahoo/Stooq market providers are end-of-day price/volume only. Configure Alpaca and Finnhub/SEC layers for near-real-time quote, fundamentals, news, filings, short interest, options, and analyst trend context.
- Five-year detail charts are daily provider charts. True streaming real-time charts require a licensed real-time market-data provider.
- Manual CSV mode can use your own current data, but the app does not verify that the data is market-accurate.
- Public demo mode has a deployment-token gate; SaaS mode has per-user auth APIs but still lacks OAuth/MFA production hardening.
- Neon PostgreSQL is connected for the current production SaaS control-plane smoke path.
- Queue APIs, worker command, protected worker endpoint, and daily Vercel Cron route exist. Historical queue tests passed, but they do not prove current live-provider market-universe readiness while Alpaca diagnostics return `ready=false`.
- Hosted `/api/health` load smoke passed after PostgreSQL cutover; it does not replace current scan-heavy queue/provider load testing after live provider credentials are fixed.
- Terms, Privacy, and Risk Disclosure drafts exist, but they are not legal-reviewed launch documents.
- No automatic trading or broker integration.
- Decision-support only; the CLI does not provide trading instructions.
- Original source docs contain encoding damage, so execution docs in this README/SETUP/OPERATIONS are authoritative for this version.

## 1000-User SaaS Planning

This repository now includes a target design and a production control-plane smoke path for a future 1000-user SaaS version. The app is still not unrestricted public-SaaS ready.

Start here:

- [1000-user architecture](docs/SAAS_1000_USER_ARCHITECTURE.md)
- [Multi-tenant data model](docs/MULTI_TENANT_DATA_MODEL.md)
- [API contract](docs/API_CONTRACT_V1.md)
- [Security and compliance plan](docs/SECURITY_COMPLIANCE_1000_USER.md)
- [Operations plan](docs/OPERATIONS_1000_USER.md)
- [Migration plan](docs/SAAS_MIGRATION_PLAN.md)
- [Load test plan](docs/LOAD_TEST_PLAN.md)
- `tools/queue_load_test.py`: local queue-backed 1000-user scan simulation.
- `tools/host_queue_load_test.py`: hosted auth/watchlist/queue smoke test.

Check current blockers:

```powershell
python -m vcb_alt saas-readiness
```

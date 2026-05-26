# VCB-Alt

Local-first US stock screening decision-support CLI and token-protected web dashboard.

VCB-Alt helps an operator evaluate watchlist tickers across seven stock archetypes, review risk notes, keep an auditable SQLite log, and run a browser dashboard. It does not place trades and does not call external market-data providers unless explicitly enabled.

## Major Features

- Local SQLite setup with `init-db`
- Watchlist add/list/remove/seed commands
- Single ticker evaluation with validation and risk warnings
- Watchlist scan with empty/success/error-safe states
- Manual CSV data provider for operator-supplied real snapshots
- Yahoo chart and optional Stooq end-of-day market-data providers with local cache
- Optional Alpaca near-real-time quote/snapshot layer with a short TTL cache
- Technical Momentum scoring for automatic market data with a data-quality gate that blocks chart-only final selections
- Optional `data/enrichment.csv` overlay for fundamentals, catalysts, short/options, insider, float, and related context
- Optional Finnhub research-data provider for fundamentals, earnings surprise, news catalysts, analyst trends, short interest, options open interest, and insider transactions
- Optional SEC submissions metadata layer for recent filing context
- Deterministic AI explanation layer, with optional OpenAI Responses API summaries when explicitly configured
- Portfolio candidate selection with position, archetype, and high-volatility constraints
- Local web dashboard with watchlist, scan table, final selection, and operations status
- Decision-first public-beta UI with SaaS-safe review labels, scoring-version visibility, and legal/disclosure links
- Click-through ticker analysis pages with five-year chart, sector/industry, current status, and selection rationale
- Responsive dashboard and ticker detail pages for desktop, mobile, and browser zoom
- Korean/English language toggle for the public dashboard and ticker analysis page
- Provider status API that reports market-data capabilities without exposing secrets
- Disabled-by-default per-user auth boundary with tenant-scoped watchlist APIs for SaaS migration testing
- Optional PostgreSQL adapter and target schema under `migrations/postgres`
- Database-backed rate limiting and queue-backed scan job APIs for SaaS migration testing
- Local 1000-user load simulation tool and hosted health load-test tool
- Optional public web mode with a deployment access token
- Throughput benchmark command
- Operator logs, failed-job history, export, and destructive delete confirmation
- Secret-redacted logging
- Offline deterministic sample data for first-run private beta testing
- Python stdlib-first runtime with `psycopg[binary]` required when PostgreSQL mode is enabled

## Tech Stack

- Python 3.11+
- SQLite for local development
- PostgreSQL/Neon for production SaaS mode
- `psycopg[binary]` for PostgreSQL connectivity
- `argparse`, `sqlite3`, `unittest`, and other Python standard-library modules

## Local Setup

```powershell
# Optional but recommended
Copy-Item .env.example .env

# Install runtime dependencies, including the PostgreSQL driver used by production SaaS mode.
python -m pip install .

# Initialize local database and seed sample tickers.
python -m vcb_alt init-db --seed

# Verify configuration.
python -m vcb_alt doctor
```

On this Windows machine, `python` is not on PATH. The verified fallback runtime is:

```powershell
& 'C:\stable-diffusion-ui\installer_files\env\python.exe' -m vcb_alt init-db --seed
```

## Environment Variables

Required for MVP: none.

Recommended:

```dotenv
VCB_ALT_DATABASE_URL=sqlite:///./data/vcb_alt.db
VCB_ALT_LOG_LEVEL=INFO
VCB_ALT_TIMEZONE=Asia/Seoul
VCB_ALT_DATA_PROVIDER=sample
VCB_ALT_EXTERNAL_API_ENABLED=false
VCB_ALT_MARKET_DATA_TIMEOUT_SECONDS=10
VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS=12
VCB_ALT_PUBLIC_WEB_ENABLED=false
VCB_ALT_WEB_ACCESS_TOKEN=replace-with-at-least-16-random-characters
VCB_ALT_AUTO_SEED_SAMPLE=true
```

`sample` is the safe offline default. `manual` reads `data/snapshots.csv`. `yahoo` fetches end-of-day chart data and requires `VCB_ALT_EXTERNAL_API_ENABLED=true`. `stooq` is also supported, but some Stooq downloads require an API key/captcha flow.

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

`finnhub` attempts to enrich each market snapshot with fundamentals, earnings surprise, recent company news, analyst recommendation trends, insider transactions, short interest, and option-chain open interest. Use `finnhub_csv` when you want Finnhub data first and `data/enrichment.csv` as an operator-reviewed override. Missing or failed research calls do not crash the scan; they leave the data coverage low so final selection remains blocked.

For near-real-time quote context:

```dotenv
VCB_ALT_INTRADAY_DATA_PROVIDER=alpaca
VCB_ALT_ALPACA_API_KEY=replace-with-your-key
VCB_ALT_ALPACA_API_SECRET=replace-with-your-secret
VCB_ALT_ALPACA_DATA_FEED=iex
VCB_ALT_INTRADAY_CACHE_TTL_SECONDS=60
```

For SEC filing context and AI explanations:

```dotenv
VCB_ALT_SEC_COMPANY_FACTS_ENABLED=true
VCB_ALT_SEC_USER_AGENT=vcb-alt-stock-screener your-email@example.com
VCB_ALT_AI_SUMMARY_PROVIDER=template
# Optional paid AI summary mode:
VCB_ALT_AI_SUMMARY_PROVIDER=openai
VCB_ALT_OPENAI_API_KEY=replace-with-your-key
VCB_ALT_OPENAI_MODEL=gpt-4.1-mini
```

The default AI provider is `template`, which creates a deterministic summary from the exact score, data coverage, chart, sector, filings, news, options, and analyst fields already present in the API response. `openai` mode calls the OpenAI Responses API only when a key is configured and falls back to the local summary if the call fails.

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

Public demo deployment is now supported behind a deployment token. See `PUBLIC_DEPLOYMENT.md`, `DEPLOYMENT.md`, and `OPERATIONS.md`.

1000-user SaaS mode is guarded by `VCB_ALT_PRODUCTION_SAAS_MODE=true`. The app refuses to start that mode unless PostgreSQL, per-user auth, database-backed rate limiting, and scan queue are enabled together. Production rate limiting is endpoint-specific: `VCB_ALT_AUTH_RATE_LIMIT_PER_MINUTE`, `VCB_ALT_USER_RATE_LIMIT_PER_MINUTE`, and `VCB_ALT_WORKER_RATE_LIMIT_PER_MINUTE` separate signup/auth bursts, authenticated tenant usage, and protected worker execution.

Latest hosted 1000-user verification:

```powershell
C:\stable-diffusion-ui\installer_files\env\python.exe tools\host_queue_load_test.py --base-url https://stockscreeningver10.vercel.app --users 1000 --concurrency 20 --tickers PLTR,MSTR,VST --timeout 30 --poll-seconds 300 --trigger-worker --worker-limit 100 --simulate-distributed-ips --confirm-production-load
```

Result: `1000` queued jobs, `1000` completed jobs, `0` errors on production deployment `dpl_8BAYrCsBPhRtgoGsp3zkxSrsZ5v5`.

Ticker detail pages:

```text
http://127.0.0.1:8765/ticker/AAPL
```

The detail page shows a five-year daily price/volume chart when the provider supports history data. Current no-key providers are labeled as end-of-day/delayed data, not tick-by-tick real-time data.

Public-beta safety documents:

- [Terms draft](TERMS.md)
- [Privacy notice draft](PRIVACY.md)
- [Risk disclosure draft](RISK_DISCLOSURE.md)

These drafts are operational placeholders and require legal review before broad public launch.

## Research And Planning

- [Deep system research](research.md): current architecture, runtime flow, provider behavior, scoring, web/API, operations, risks, and scaling constraints.
- [Operator trial guide](OPERATOR_TRIAL_GUIDE.md): owner pre-user usage URL, workflow checklist, provider mode, and public-launch blockers.
- [Provider keys setup](PROVIDER_KEYS_SETUP.md): safe Vercel/local setup for Alpaca, Finnhub, SEC, and OpenAI keys.
- [OAuth/MFA/RBAC plan](AUTH_MFA_RBAC_PLAN.md): auth hardening and role matrix before unrestricted public launch.
- [Monitoring and alerting plan](MONITORING_ALERTING_PLAN.md): operational dashboards, alerts, and health-report tooling.
- [Neon backup/restore drill](NEON_BACKUP_RESTORE_DRILL.md): staging-first recovery drill and evidence checklist.
- [Legal review packet](LEGAL_REVIEW_PACKET.md): counsel-facing launch review checklist and official reference links.
- [Feature 00 implementation plan](plan.md): input-based/keyset paging plan for list APIs without SQL `OFFSET`.
- [QA report](QA_REPORT.md): latest executed verification results.
- [Release decision](RELEASE_DECISION.md): current beta readiness and remaining public-SaaS blockers.
- [SaaS implementation plan](SAAS_IMPLEMENTATION_PLAN.md): next public-beta and 1000-user architecture path.
- [PostgreSQL migration](migrations/postgres/001_saas_core.sql): target SaaS tenant/user/session/watchlist/evaluation/rate-limit/job schema.

## Known Limitations

- Yahoo/Stooq market providers are end-of-day price/volume only. Configure Alpaca and Finnhub/SEC layers for near-real-time quote, fundamentals, news, filings, short interest, options, and analyst trend context.
- Five-year detail charts are daily provider charts. True streaming real-time charts require a licensed real-time market-data provider.
- Manual CSV mode can use your own current data, but the app does not verify that the data is market-accurate.
- Public demo mode has a deployment-token gate; SaaS mode has per-user auth APIs but still lacks OAuth/MFA production hardening.
- Neon PostgreSQL is connected for the current production SaaS control-plane smoke path.
- Queue APIs, worker command, protected worker endpoint, and daily Vercel Cron route exist; scan-heavy queue load tests are still pending.
- Hosted `/api/health` load smoke passed after PostgreSQL cutover; it does not replace scan-heavy queue/provider load testing.
- Terms, Privacy, and Risk Disclosure drafts exist, but they are not legal-reviewed launch documents.
- No automatic trading or broker integration.
- No investment advice; the CLI is decision-support only.
- Original source docs contain encoding damage, so execution docs in this README/SETUP/OPERATIONS are authoritative for this version.

## 1000-User SaaS Planning

This repository now includes a target design and a production control-plane smoke path for a future 1000-user SaaS version. The app is still not unrestricted public-SaaS ready.

Start here:

- [1000-user architecture](SAAS_1000_USER_ARCHITECTURE.md)
- [Multi-tenant data model](MULTI_TENANT_DATA_MODEL.md)
- [API contract](API_CONTRACT_V1.md)
- [Security and compliance plan](SECURITY_COMPLIANCE_1000_USER.md)
- [Operations plan](OPERATIONS_1000_USER.md)
- [Migration plan](SAAS_MIGRATION_PLAN.md)
- [Load test plan](LOAD_TEST_PLAN.md)
- `tools/queue_load_test.py`: local queue-backed 1000-user scan simulation.
- `tools/host_queue_load_test.py`: hosted auth/watchlist/queue smoke test.

Check current blockers:

```powershell
python -m vcb_alt saas-readiness
```

# Deployment Guide

## Current Deployment Target

The current release target is a controlled private beta or token-protected public demo. It is not yet a full 1000-user multi-tenant SaaS.

## Local Private Beta Deployment

1. Place the project folder on the operator machine.
2. Confirm Python 3.11+ is available.
3. Copy `.env.example` to `.env`.
4. Keep `VCB_ALT_EXTERNAL_API_ENABLED=false` unless you are testing a configured market-data provider.
5. Run:

```powershell
python -m pip install .
python -m vcb_alt init-db --seed
python -m vcb_alt self-test
python -m vcb_alt scan
```

## Token-Protected Public Demo

Set:

```dotenv
VCB_ALT_DATA_PROVIDER=yahoo
VCB_ALT_EXTERNAL_API_ENABLED=true
VCB_ALT_PUBLIC_WEB_ENABLED=true
VCB_ALT_WEB_ACCESS_TOKEN=<long-random-token>
```

Run:

```powershell
python -m vcb_alt web --host 0.0.0.0 --port 8765
```

Open `/?token=<long-random-token>` once to establish the HTTP-only cookie.

For Docker or Render deployment, see `PUBLIC_DEPLOYMENT.md`, `Dockerfile`, and `render.yaml`.

## Data Locations

- SQLite DB: `data/vcb_alt.db`
- Production SaaS DB: managed PostgreSQL/Neon via `VCB_ALT_DATABASE_URL`
- App logs: `logs/app.log`
- Exported JSON: operator-chosen path, recommended under `exports/`

## 1000-User SaaS Deployment Gate

This gate is now enabled for the production control-plane smoke path. Do not open unrestricted public signup until hosted scan-heavy load tests, backup/restore, monitoring, auth hardening, WAF/proxy hardening, and legal review are complete.

Required production variables:

```dotenv
VCB_ALT_DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require
VCB_ALT_USER_AUTH_ENABLED=true
VCB_ALT_USER_REGISTRATION_ENABLED=true
VCB_ALT_RATE_LIMIT_BACKEND=database
VCB_ALT_SCAN_QUEUE_ENABLED=true
VCB_ALT_WORKER_CRON_ENABLED=true
VCB_ALT_WORKER_TOKEN=<long-random-worker-token>
VCB_ALT_PRODUCTION_SAAS_MODE=true
```

PostgreSQL runtime dependency:

```powershell
python -m pip install .
```

Initialize durable tables:

```powershell
python -m vcb_alt init-db
```

Run the worker:

```powershell
python -m vcb_alt worker run-once --limit 25
```

The Vercel deployment also includes a daily Hobby-compatible Cron route:

```text
/api/admin/run-worker?limit=25
```

This route stays inert while `VCB_ALT_WORKER_CRON_ENABLED=false`. When enabling it on Vercel, set `CRON_SECRET` and `VCB_ALT_WORKER_TOKEN` to the same long random value so the cron request bearer token can authenticate the worker endpoint.

For hosted load smoke after deployment:

```powershell
python tools/host_load_test.py --url https://stockscreeningver10.vercel.app/api/health --requests 1000 --concurrency 25 --timeout 15
```

2026-05-22 hosted result: `1000/1000` health requests returned `200` with `0` errors and p95 latency `2120.62ms`.

2026-05-22 Neon cutover result:

- Vercel Marketplace Neon resource is connected.
- `VCB_ALT_DATABASE_URL` points to the pooled Neon PostgreSQL URL.
- Production reports `production_saas_ready=true`.
- SaaS smoke passed for registration, tenant watchlist, queue, worker, and job lookup.
- Post-cutover hosted health load result: `1000/1000` requests returned `200`, `0` errors, p95 latency `1917.36ms`.

## Backup

Stop running commands first, then copy:

```powershell
Copy-Item data\vcb_alt.db backups\vcb_alt_YYYYMMDD.db
```

## Rollback

1. Stop using the CLI.
2. Replace `data/vcb_alt.db` with a known-good backup.
3. Run `python -m vcb_alt doctor`.
4. Run `python -m vcb_alt admin logs`.

## Public Deployment Blockers

- Token gate exists, and per-user session APIs now exist, but MFA/OAuth/RBAC are not production complete.
- No privacy policy or legal review for multi-user investment tooling.
- Market-data providers have deterministic unit tests and cache behavior tests, but no live contract test in CI.
- Neon PostgreSQL is configured in Vercel Production for the current control-plane smoke path.
- Queue APIs, worker command, protected worker endpoint, and Vercel Cron route are wired.
- Hosted `/api/health` load smoke passed; scan-heavy queue/provider load testing is still pending.
- WAF/proxy hardening and centralized observability are still required.

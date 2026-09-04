# Neon Backup And Restore Drill

Last updated: 2026-06-03 KST

## Current Readiness

Current status: `operator_trial`, not public SaaS.

The 2026-06-03 redacted operations check against `https://stockscreeningver10.vercel.app` returned `overall_status=ok`, `production_saas_ready=true`, `public_launch_ready=false`, PostgreSQL-backed configuration, queue enabled, and worker cron enabled. This confirms production is wired to Neon/PostgreSQL for the operator-trial control plane. It does not prove backup/restore readiness because a restore drill has not been executed in Neon.

Backup/restore status: `PENDING_OPERATOR_NEON_DRILL`.

Reason: restore requires Neon console/API access and an explicit staging target. Do not perform destructive restore tests on the production branch.

## Objective

Prove that tenant data can be restored after accidental deletion, failed migration, DB corruption, or a bad deployment without leaking secrets and without cross-tenant data exposure.

## Required Access

- Neon project console access with permission to create branches and point-in-time restores.
- Vercel project access for staging environment variable updates.
- `psql` and `pg_dump` installed on the operator workstation.
- A staging app URL connected to a Neon staging/restored branch.
- A redacted evidence folder such as `data/restore-drills/20260603/`.

Never paste `DATABASE_URL`, passwords, provider keys, session tokens, or worker tokens into documents, tickets, screenshots, or command output.

## Target RTO/RPO

Owner/operator trial target:

- RTO: restore verified within 4 hours.
- RPO: no more than 24 hours of data loss.

Public or paid launch target, pending business/legal approval:

- RTO: restore verified within 1 hour.
- RPO: 15 minutes or better, depending on the Neon plan and backup configuration.

These targets are not yet proven. Record actual values after the first staging drill.

## Environment Variables For The Drill

Set these only in the current shell. Do not commit them.

```powershell
$env:BASE_URL="https://stockscreeningver10.vercel.app"
$env:STAGING_BASE_URL="https://<staging-app-host>"
$env:STAGING_DATABASE_URL="<neon-staging-or-restore-branch-url>"
$env:DRILL_EMAIL="neon-drill-$(Get-Date -Format yyyyMMddHHmmss)@example.test"
$env:DRILL_PASSWORD="Drill!2026-Temporary"
New-Item -ItemType Directory -Force data\restore-drills\20260603
```

## Step 1. Production Control-Plane Preflight

Run a redacted hosted health report:

```powershell
python tools\ops_health_report.py --base-url $env:BASE_URL --timeout 20
```

Expected:

- `overall_status=ok`
- `release_channel=operator_trial`
- `public_launch_ready=false`
- `database_backend=postgresql`
- `queue_enabled=true`
- `worker_cron_enabled=true`

If the health report is degraded, stop the restore drill and open an incident first.

## Step 2. Create A Neon Staging Branch

Use the Neon console:

1. Open the production Neon project.
2. Create a new branch from the production parent branch.
3. Name it `staging-restore-drill-YYYYMMDD`.
4. Use the latest safe restore point.
5. Copy the branch connection string into the local shell as `STAGING_DATABASE_URL`.
6. Attach the staging app or preview environment to this branch only.

Do not point production Vercel to the staging/restored branch during the drill.

## Step 3. Migration Drift Check

Apply the idempotent schema file to staging:

```powershell
psql $env:STAGING_DATABASE_URL -v ON_ERROR_STOP=1 -f migrations\postgres\001_saas_core.sql
```

Export a schema-only snapshot for evidence:

```powershell
pg_dump --schema-only --no-owner --no-privileges $env:STAGING_DATABASE_URL > data\restore-drills\20260603\schema-staging.sql
```

Verify required tables:

```powershell
psql $env:STAGING_DATABASE_URL -v ON_ERROR_STOP=1 -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('tenants','users','sessions','tenant_watchlist','tenant_evaluations','audit_events','rate_limit_events','scan_jobs','market_scan_snapshots','provider_alert_events') ORDER BY table_name;"
```

Verify required indexes:

```powershell
psql $env:STAGING_DATABASE_URL -v ON_ERROR_STOP=1 -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname IN ('idx_users_tenant','idx_sessions_token','idx_tenant_watchlist_user','idx_tenant_evaluations_latest','idx_audit_events_tenant_time','idx_rate_limit_events_key_time','idx_scan_jobs_status_time','idx_scan_jobs_tenant_user_time','idx_market_scan_snapshots_key_time','idx_market_scan_snapshots_status_time','idx_market_scan_snapshots_active','idx_provider_alert_events_time','idx_provider_alert_events_provider_time') ORDER BY indexname;"
```

Pass condition: all required tables and indexes exist, and the schema migration command exits successfully.

## Step 4. Create Sample Tenant Baseline

Run this against the staging app, not production:

```powershell
$register = Invoke-RestMethod -Uri "$env:STAGING_BASE_URL/api/auth/register" -Method POST -ContentType "application/json" -Body (@{
  email=$env:DRILL_EMAIL
  password=$env:DRILL_PASSWORD
  tenant_name="Neon Restore Drill"
} | ConvertTo-Json)
$env:DRILL_TOKEN=$register.data.session_token
$env:DRILL_TENANT_ID=$register.data.user.tenant_id
Invoke-RestMethod -Uri "$env:STAGING_BASE_URL/api/user/watchlist" -Method POST -Headers @{Authorization="Bearer $env:DRILL_TOKEN"} -ContentType "application/json" -Body (@{tickers="PLTR MSTR VST"} | ConvertTo-Json)
```

Record baseline row counts:

```powershell
psql $env:STAGING_DATABASE_URL -v tenant_id="$env:DRILL_TENANT_ID" -v ON_ERROR_STOP=1 -c "SELECT 'users' AS table_name, COUNT(*) FROM users WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'sessions', COUNT(*) FROM sessions WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'tenant_watchlist', COUNT(*) FROM tenant_watchlist WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'scan_jobs', COUNT(*) FROM scan_jobs WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'tenant_evaluations', COUNT(*) FROM tenant_evaluations WHERE tenant_id=:'tenant_id';"
```

Export sample tenant data through the API:

```powershell
Invoke-RestMethod -Uri "$env:STAGING_BASE_URL/api/user/export" -Method GET -Headers @{Authorization="Bearer $env:DRILL_TOKEN"} | ConvertTo-Json -Depth 8 > data\restore-drills\20260603\sample-tenant-export-before.json
```

Pass condition: exactly one sample user exists in one tenant, watchlist count is `3`, and API export does not include another tenant's data.

## Step 5. Simulate Staging Data Loss

Use staging only:

```powershell
psql $env:STAGING_DATABASE_URL -v tenant_id="$env:DRILL_TENANT_ID" -v ON_ERROR_STOP=1 -c "DELETE FROM tenant_watchlist WHERE tenant_id=:'tenant_id';"
psql $env:STAGING_DATABASE_URL -v tenant_id="$env:DRILL_TENANT_ID" -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) AS watchlist_rows_after_delete FROM tenant_watchlist WHERE tenant_id=:'tenant_id';"
```

Pass condition: staging sample tenant data is missing and the failure is observable. Do not proceed if the command targeted production.

## Step 6. Restore To A New Neon Branch

Use the Neon console:

1. Create a point-in-time restore branch from the staging source branch.
2. Choose a timestamp after the baseline was created and before the deletion simulation.
3. Name the branch `staging-restore-drill-restored-YYYYMMDD`.
4. Copy the restored branch connection string to `STAGING_DATABASE_URL`.
5. Repoint only the staging app or local verification shell to the restored branch.

Do not overwrite or drop the original staging branch until evidence is reviewed.

## Step 7. Restore Verification

Run migration drift check again:

```powershell
psql $env:STAGING_DATABASE_URL -v ON_ERROR_STOP=1 -f migrations\postgres\001_saas_core.sql
```

Verify tenant data returned:

```powershell
psql $env:STAGING_DATABASE_URL -v tenant_id="$env:DRILL_TENANT_ID" -v ON_ERROR_STOP=1 -c "SELECT 'users' AS table_name, COUNT(*) FROM users WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'sessions', COUNT(*) FROM sessions WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'tenant_watchlist', COUNT(*) FROM tenant_watchlist WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'scan_jobs', COUNT(*) FROM scan_jobs WHERE tenant_id=:'tenant_id' UNION ALL SELECT 'tenant_evaluations', COUNT(*) FROM tenant_evaluations WHERE tenant_id=:'tenant_id';"
```

Verify API health:

```powershell
python tools\ops_health_report.py --base-url $env:STAGING_BASE_URL --timeout 20
```

Pass condition:

- Staging app returns healthy status.
- Sample tenant row counts match the baseline.
- Watchlist count returns to `3`.
- API export works for the sample tenant.
- A second tenant cannot access sample tenant data.

## Step 8. RTO/RPO Evidence

Record:

- Incident simulation start time.
- Deletion confirmed time.
- Restore branch creation start time.
- Restore branch ready time.
- App verification completed time.
- Restore point timestamp.

Calculate:

- RTO = app verification completed time - incident simulation start time.
- RPO = deletion confirmed time - restore point timestamp.

Store only redacted evidence in `data/restore-drills/20260603/`.

## Rollback Procedure

Use this if a migration, deployment, or database change breaks production.

1. Declare incident and stop broad user access.
2. Disable or pause worker execution so new provider-heavy writes stop.
3. Preserve the broken production branch for forensics; do not drop it.
4. Create a Neon point-in-time restore branch from before the bad change.
5. Run migration drift and sample tenant integrity checks against the restore branch.
6. Update Vercel production `DATABASE_URL` to the restore branch only after verification.
7. Redeploy or promote the previous known-good Vercel deployment.
8. Run `/api/health`, `/api/release-status`, `/api/provider-health`, auth login, snapshot read, and admin queue checks.
9. Keep the incident open until root cause, data-loss scope, and user communication requirements are documented.

Rollback is not complete until tenant isolation and sample tenant export pass.

## Pass/Fail Decision

Pass:

- Staging point-in-time restore succeeds.
- Migration drift check passes after restore.
- Sample tenant integrity check passes.
- RTO/RPO are recorded and meet the current target.
- No secrets are exposed in evidence.

Fail:

- Restore requires undocumented manual steps.
- App cannot reconnect to the restored branch.
- Tenant baseline does not return.
- Cross-tenant data is visible.
- RTO/RPO exceed the target without a documented mitigation.

## Current Result

Status: pending operator-side Neon staging restore execution.

Next required action: create the staging restore branch in Neon, run the commands above, and attach the evidence file paths to `QA_REPORT.md`.

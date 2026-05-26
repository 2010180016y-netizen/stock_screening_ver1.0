# Neon Backup And Restore Drill

Last updated: 2026-05-22 KST

## Current State

- Neon PostgreSQL is connected to Vercel production through the Marketplace integration.
- The app uses PostgreSQL for the production SaaS control-plane smoke path.
- A backup/restore drill has not yet been executed in this workspace because it requires operator access to the Neon project console or Neon API credentials.

## Goal

Prove that production tenant data can be recovered after accidental deletion, failed migration, or provider outage without exposing secrets in logs or docs.

## Drill Scope

Use a staging branch/database first. Do not run destructive restore tests against production until the staging drill succeeds.

## Drill Steps

1. Confirm Neon project and branch:
   - Project name.
   - Database name.
   - Branch name.
   - Latest backup/restore point availability.

2. Create staging test data:
   - Register a staging user.
   - Add watchlist tickers.
   - Queue a scan.
   - Run worker.
   - Record job ID and tenant ID internally.

3. Capture baseline:
   - Count users, tenants, watchlist rows, scan jobs, tenant evaluations.
   - Save counts only, not secrets.

4. Simulate failure on staging:
   - Delete staging tenant data.
   - Confirm user flow fails or data is missing.

5. Restore:
   - Restore Neon branch/database to a point before deletion.
   - Reattach staging environment if a new branch URL is issued.
   - Run app smoke checks.

6. Verify:
   - Health endpoint returns `200`.
   - User login works.
   - Watchlist rows are back.
   - Job history is back.
   - Tenant isolation still passes.

7. Record evidence:
   - Restore started time.
   - Restore completed time.
   - RTO.
   - RPO.
   - Verification command results.
   - Any manual steps required.

## Pass Criteria

- Staging restore completes without secret exposure.
- App can reconnect to the restored database.
- Tenant data returns to the expected baseline.
- No cross-tenant data exposure occurs.
- RTO/RPO are acceptable for private beta.

## Current Result

Status: pending operator-side Neon console/API execution.

Reason: Codex can prepare the drill and run app-level verification, but cannot safely perform Neon restore actions without explicit Neon API credentials and a selected staging target.

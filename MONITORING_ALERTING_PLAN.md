# Monitoring And Alerting Plan

Last updated: 2026-05-22 KST

## Current State

- `/api/health` reports process health.
- `/api/release-status` reports production SaaS configuration state.
- `/api/provider-status` reports provider configuration and warnings without exposing secrets.
- `/api/saas-readiness` reports launch blockers.
- `tools/ops_health_report.py` now collects a redacted operations summary and can send it to a webhook.
- Local `operation_logs` and `failed_jobs` exist.

## Required Dashboards

1. API health:
   - 2xx/4xx/5xx counts.
   - p50/p95/p99 latency.
   - request rate.
   - rate-limit rejects.

2. Queue health:
   - queued jobs.
   - running jobs.
   - failed jobs.
   - oldest queued age.
   - worker processed/failed count.

3. Provider health:
   - Yahoo/Stooq/Finnhub/Alpaca/SEC request count.
   - provider failure count.
   - cache hit rate.
   - budget exhaustion.

4. Database health:
   - Neon connection count.
   - query latency.
   - lock wait.
   - storage growth.
   - backup status.

5. Security:
   - login failure spike.
   - new registration spike.
   - unusual scan queue volume.
   - worker endpoint auth failures.

## Alert Rules

| Alert | Threshold | Severity |
|---|---:|---|
| API 5xx rate | > 2% for 5 minutes | P1 |
| Health check failure | 2 consecutive failures | P1 |
| Queue oldest job age | > 10 minutes | P1 |
| Worker failures | > 5 failures in 10 minutes | P1 |
| Provider failures | > 20% for 10 minutes | P1 |
| Rate limit rejects | > 10% for 5 minutes | P2 |
| Login failures | > 20 per IP/hour | P1 |
| Neon connection saturation | > 80% for 5 minutes | P1 |
| Backup missing | no successful backup in 24 hours | P1 |

## Command

```powershell
python tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app
```

Optional webhook:

```powershell
$env:VCB_ALT_ALERT_WEBHOOK_URL="https://hooks.example.invalid/..."
python tools\ops_health_report.py --base-url https://stockscreeningver10.vercel.app --send-alert
```

## Remaining Work

- Connect Vercel/Neon metrics to a durable monitoring system.
- Add request IDs to API responses and logs.
- Add queue-depth endpoint or admin-only dashboard.
- Add provider budget counters.
- Add alert destination owned by the operator.

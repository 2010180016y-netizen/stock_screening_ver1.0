# Operations Plan For 1000 Users

Last updated: 2026-05-16

## 1. Service Level Objectives

Private 1000-user beta SLO:

- API availability: 99.5%
- Cached read p95 latency: < 500 ms
- On-demand cached evaluation p95 latency: < 2 s
- Daily scan completion: < 30 min
- Error rate: < 1% for API requests excluding client validation errors

## 2. Dashboards

Minimum dashboards:

- API requests by endpoint, status, and latency
- Auth/login failures
- Job queue depth and job age
- Worker success/failure rate
- Provider request count, latency, and errors
- PostgreSQL CPU, connections, locks, slow queries
- Redis memory and evictions
- User signups/DAU/scan completions

## 3. Alerts

Page/on-call:

- API 5xx > 2% for 5 minutes
- DB unavailable
- Queue oldest job age > 15 minutes
- Daily scan not completed by target time
- Provider failure rate > 20%
- Auth error spike

Ticket/business-hours:

- Provider budget reaches 80%
- Slow query p95 regression
- Export/delete job failures

## 4. Runbooks

Need runbooks for:

- Provider outage
- Queue backlog
- DB connection exhaustion
- Failed migration
- Bad scoring release rollback
- User data export failure
- User deletion failure
- Suspected tenant isolation incident

## 5. Deployment Pipeline

Required stages:

1. Unit tests
2. API contract tests
3. Authorization tests
4. Worker/job tests
5. Migration dry run
6. Build container images
7. Deploy staging
8. Smoke test staging
9. Canary production
10. Monitor and promote

## 6. Load Testing Plan

Scenarios:

- 100 concurrent login/session reads
- 100 concurrent latest-evaluation reads
- 50 concurrent watchlist updates
- 1000 daily scan jobs with 30 tickers each
- Provider outage during scan
- Redis unavailable
- PostgreSQL slow query simulation

Pass criteria:

- No data crossing tenants.
- No unbounded queue growth.
- No provider budget breach.
- p95 latency within SLO for cached reads.
- Failed jobs are visible to operators.


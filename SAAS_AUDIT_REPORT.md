# 1000-User SaaS Audit Report

Audit date: 2026-05-16

## 1. Current Product Definition

The current product is a local, single-operator Python CLI for sample/offline stock screening. It is not a multi-user web product.

## 2. Target Product Definition

The 1000-user version should be an authenticated SaaS decision-support platform where users maintain watchlists, run delayed-data/cached stock screens, review results, and manage their data without automatic trading.

## 3. Expert Review Synthesis

Three parallel reviews were run:

- Scale architecture: confirmed the current CLI/SQLite design cannot be safely wrapped as a public service.
- Security/compliance: flagged auth, tenant isolation, investment-advice risk, privacy/delete/export, secrets, logs, and rate limits as launch blockers.
- Product/operations/SRE: flagged missing signup/dashboard/admin/queue/monitoring/support/load-test flows.

## 4. P0 Blockers

- No authentication, sessions, MFA, or account model.
- No tenant isolation or user ownership in current SQLite tables.
- No public HTTP API or frontend.
- No PostgreSQL schema, migrations, backups, or restore process.
- No background job queue for 1000 daily scans.
- No legal/compliance review for investment-decision language.
- No SaaS privacy/export/delete workflow.
- No production observability, alerts, or incident process.

## 5. P1 Blockers

- No provider adapters, request budgets, or live-data contract tests.
- No rate limiting, abuse controls, or signup throttling.
- No admin RBAC dashboard.
- No load tests or concurrency tests.
- No support/helpdesk/status-page process.
- No migration pipeline or staging environment.

## 6. Existing Strengths To Reuse

- Ticker validation rejects unsafe input.
- SQL writes use parameterized queries.
- External APIs are disabled by default.
- Secret redaction helpers exist.
- Local destructive deletion requires explicit confirmation.
- Scoring logic is deterministic and testable.

## 7. What Must Not Be Done

- Do not expose the current CLI over HTTP.
- Do not add 1000 users to the current SQLite schema.
- Do not enable paid/live APIs without budgets, retries, caching, and tests.
- Do not market `BUY_CANDIDATE`, suggested size, or stop loss as personalized investment advice.
- Do not skip legal/privacy review.

## 8. Correct Path

1. Treat current code as a domain prototype.
2. Build a new SaaS platform boundary: web app, API, auth, PostgreSQL, Redis, queue workers, observability.
3. Move scoring to a versioned domain package.
4. Add tenant/user/account data model.
5. Add legal-reviewed product language.
6. Run staging load/security/compliance gates before 1000-user beta.


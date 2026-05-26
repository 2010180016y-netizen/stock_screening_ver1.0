# SaaS Migration Plan

Last updated: 2026-05-16

## Phase 0: Current State

Status: local CLI private beta.

Use it only as:

- Domain-scoring prototype
- Validation behavior reference
- Local export source

Do not use it as:

- Shared server
- Public API
- Production DB

## Phase 1: Domain Hardening

Goal: make scoring reusable and testable as a pure library.

Tasks:

- Add scoring version constant.
- Add schema-versioned evaluation output.
- Add fixture-based tests for all seven current archetypes, including `G_TECHNICAL_MOMENTUM`.
- Separate data-provider snapshots from scoring decisions.
- Add benchmark tests for 500 and 2000 ticker evaluations.

Exit criteria:

- Domain tests pass.
- No DB or CLI dependency inside scoring.
- Evaluation result includes scoring version.

## Phase 2: API Prototype

Goal: authenticated single-tenant API with no public launch.

Tasks:

- Build API skeleton.
- Add auth provider.
- Add PostgreSQL schema.
- Add tenant/user/watchlist/evaluation endpoints.
- Add authorization tests.
- Add rate limiting.

Exit criteria:

- User A cannot access User B data in tests.
- API supports add ticker and cached evaluation.

## Phase 3: Worker And Provider Layer

Goal: production-like scanning pipeline.

Tasks:

- Add queue workers.
- Add provider adapter interface.
- Add provider budget table and enforcement.
- Add stale-cache strategy.
- Add dead-letter queue.

Exit criteria:

- 1000 scan jobs can be queued and completed in staging.
- Provider failure does not crash worker fleet.

## Phase 4: Web UX And Admin

Goal: usable 1000-user beta.

Tasks:

- Build login, onboarding, watchlist, results, settings, export/delete screens.
- Build admin dashboard for users, jobs, provider status, failures.
- Add empty/loading/error/success states.
- Add accessibility pass.

Exit criteria:

- Non-developer user can complete signup to result flow.
- Operator can diagnose failed jobs.

## Phase 5: Compliance And Beta Launch

Goal: controlled 1000-user beta.

Tasks:

- Legal review.
- Privacy policy and terms.
- Security review.
- Load test.
- Backup/restore drill.
- Incident runbook drill.

Exit criteria:

- Release board signs off.
- SLO dashboards and alerts are live.
- Beta invitation cohort is capped.

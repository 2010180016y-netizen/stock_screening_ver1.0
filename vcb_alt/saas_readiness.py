from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    label: str
    status: str
    priority: str
    current_state: str
    required_state: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


READINESS_ITEMS = [
    ReadinessItem(
        key="auth",
        label="Authentication",
        status="partial",
        priority="P0",
        current_state=(
            "Shared-token demo mode still exists for controlled access. Per-user auth with password hashing, "
            "sessions, bearer-token APIs, and SaaS-mode production guards is now enabled in the production "
            "control-plane smoke path. Public-launch hardening still lacks verified email/OAuth, MFA, and RBAC."
        ),
        required_state="Verified email/OAuth auth, session handling, admin MFA, and auth tests.",
    ),
    ReadinessItem(
        key="tenant_isolation",
        label="Tenant isolation",
        status="partial",
        priority="P0",
        current_state=(
            "SaaS tables include tenants, users, sessions, and tenant-scoped watchlists with isolation tests. "
            "When user auth is enabled, legacy global watchlist/scan APIs are blocked in favor of tenant-scoped APIs. "
            "Queued scans now persist tenant evaluation history for later audit and user review."
        ),
        required_state="Tenant-scoped admin views, export/delete workflows, and deployed cross-tenant access tests.",
    ),
    ReadinessItem(
        key="api",
        label="Public API",
        status="partial",
        priority="P0",
        current_state=(
            "Token-protected scan/select APIs exist. Per-user auth, me, tenant watchlist APIs, queued scan APIs, "
            "and database-backed rate limiting are enabled in production SaaS mode."
        ),
        required_state=(
            "Authenticated HTTP API with request validation, response envelope, idempotency, "
            "and production rate-limit monitoring."
        ),
    ),
    ReadinessItem(
        key="database",
        label="Production database",
        status="partial",
        priority="P0",
        current_state=(
            "SQLite remains available for local development. Neon PostgreSQL is connected in Vercel production, "
            "the runtime PostgreSQL adapter is active in SaaS mode, and production smoke verified registration, "
            "tenant watchlist, scan queue, worker processing, and job lookup."
        ),
        required_state="Managed PostgreSQL with migration drift checks, backups, restore drills, and tenant-scoped indexes.",
    ),
    ReadinessItem(
        key="background_jobs",
        label="Background jobs",
        status="partial",
        priority="P0",
        current_state=(
            "A durable database-backed scan job table, enqueue API, job status API, "
            "worker run-once command, protected worker endpoint, and daily Vercel Cron route exist. "
            "Market-universe production scans now use worker-owned durable snapshots so user requests read a "
            "fresh shared result or enqueue/status-check a refresh instead of calling providers directly. "
            "PostgreSQL job claiming uses SKIP LOCKED, and snapshot jobs include retry, stale-running recovery, "
            "and dead-letter states."
        ),
        required_state="Worker observability, scheduled refresh policies, and hosted scan-heavy provider load evidence.",
    ),
    ReadinessItem(
        key="provider_budgeting",
        label="Provider budget and caching",
        status="partial",
        priority="P1",
        current_state=(
            "Yahoo/Stooq EOD price/volume providers exist with local cache and timeout, "
            "but no provider quota dashboard, circuit breaker, or CI live contract test."
        ),
        required_state="Provider adapters with caching, retries, circuit breakers, quotas, and contract tests.",
    ),
    ReadinessItem(
        key="observability",
        label="Observability",
        status="partial",
        priority="P1",
        current_state="Local logs, failed_jobs, release status, and worker failure records exist, but no central alerting.",
        required_state="Centralized logs, metrics, traces, dashboards, alerts, and request IDs.",
    ),
    ReadinessItem(
        key="privacy",
        label="Privacy and deletion",
        status="partial",
        priority="P1",
        current_state="Local data export/delete exists for one operator; per-user SaaS export/delete is still pending.",
        required_state="Per-user export/delete workflows, retention policy, audit-safe anonymization, and privacy policy.",
    ),
    ReadinessItem(
        key="legal",
        label="Financial/legal review",
        status="partial",
        priority="P0",
        current_state=(
            "Decision-support warnings and starter Terms/Privacy/Risk docs exist, "
            "but they are not legal-reviewed launch documents."
        ),
        required_state="Legal-reviewed disclaimers, terms, privacy policy, jurisdiction review, and no auto-trading.",
    ),
    ReadinessItem(
        key="load_testing",
        label="Load testing",
        status="partial",
        priority="P1",
        current_state=(
            "Local 1000-user / 30,000-evaluation simulation passed. Hosted /api/health load smoke passed after "
            "Neon cutover for 1000 requests at concurrency 25 with 0 errors. Historical queue-load tests exist, "
            "but current scan-heavy deployed provider load must be rerun after Alpaca diagnostics return ready."
        ),
        required_state="Staging load tests for 1000 users, 30k daily evaluations, provider outages, and tenant isolation.",
    ),
]


def get_saas_readiness() -> dict[str, object]:
    blockers = [item for item in READINESS_ITEMS if item.priority == "P0" and item.status != "ready"]
    return {
        "ready_for_1000_users": False,
        "decision": "NOT_READY_FOR_1000_USER_SAAS",
        "summary": (
            "The current product has a token-protected web app and a production SaaS control-plane smoke path "
            "with PostgreSQL, per-user auth, tenant-scoped watchlists, durable rate limiting, and queued scans. "
            "It is still not ready for unrestricted 1000-user public SaaS until auth hardening, legal review, "
            "monitoring, backup/restore, and scan-heavy hosted load tests are complete."
        ),
        "p0_blocker_count": len(blockers),
        "items": [item.to_dict() for item in READINESS_ITEMS],
    }

# Multi-Tenant Data Model

Last updated: 2026-05-16

## 1. Design Rules

- Use PostgreSQL for SaaS.
- Use UUID primary keys.
- Include `tenant_id` on all tenant-owned tables.
- Use unique constraints scoped by `tenant_id` and `user_id`.
- Never store API secrets in user tables.
- Store provider raw responses only when allowed by provider terms.
- Keep market data shared and user evaluations tenant-owned.

## 2. Core Tables

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'private_beta',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email CITEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);

CREATE TABLE watchlist_items (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    ticker TEXT NOT NULL,
    archetype_hint TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id, ticker)
);

CREATE TABLE market_snapshots (
    id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    provider TEXT NOT NULL,
    payload JSONB NOT NULL,
    freshness_state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, snapshot_date, provider)
);

CREATE TABLE evaluations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    ticker TEXT NOT NULL,
    market_snapshot_id UUID REFERENCES market_snapshots(id),
    scoring_version TEXT NOT NULL,
    primary_archetype TEXT NOT NULL,
    combined_score INTEGER NOT NULL CHECK (combined_score BETWEEN 0 AND 100),
    setup_strength TEXT NOT NULL,
    can_enter BOOLEAN NOT NULL,
    suggested_size_pct NUMERIC(5,2) NOT NULL,
    stop_loss NUMERIC(18,4) NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evaluations_user_latest
ON evaluations(tenant_id, user_id, created_at DESC);

CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    idempotency_key TEXT,
    payload JSONB NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    actor_user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    target_type TEXT,
    target_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}',
    ip_hash TEXT,
    user_agent_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 3. Data Deletion

Account deletion must:

1. Mark user `status='deletion_requested'`.
2. Revoke sessions.
3. Export user data if requested.
4. Delete or anonymize user-owned `watchlist_items`, `evaluations`, `jobs`, and audit metadata where legally allowed.
5. Keep minimal security audit records only if required and documented.

## 4. Row-Level Security Direction

If using PostgreSQL RLS:

- Set `app.tenant_id` and `app.user_id` per request transaction.
- Enable RLS on tenant-owned tables.
- Add policies restricting rows to current tenant.
- Still enforce authorization in application code; RLS is defense in depth.

## 5. Migration From Current SQLite

Current SQLite tables:

- `watchlist`
- `evaluations`
- `operation_logs`
- `failed_jobs`

Migration strategy:

- Treat current local DB as private-beta export source only.
- Export local data to JSON.
- Import watchlist rows into a single created SaaS user/tenant.
- Do not import local operation logs into multi-user production audit logs.


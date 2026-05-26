# API Contract v1

Last updated: 2026-05-19

## 1. Response Envelope

All API responses should use:

```json
{
  "ok": true,
  "request_id": "req_...",
  "data": {},
  "error": null
}
```

Error response:

```json
{
  "ok": false,
  "request_id": "req_...",
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Ticker is invalid.",
    "fields": {"ticker": "Use 1-10 uppercase ticker characters."}
  }
}
```

## 2. Status Codes

- `200`: read or synchronous mutation success
- `201`: resource created
- `202`: job queued
- `204`: delete success with no body
- `400`: validation failure
- `401`: unauthenticated
- `403`: unauthorized
- `404`: missing resource
- `409`: conflict/idempotency collision
- `422`: semantically invalid request
- `429`: rate limit
- `500`: internal error
- `503`: provider/service unavailable

## 3. Endpoint Sketch

### `GET /healthz`

No auth. Returns process health.

### `GET /readyz`

No auth. Checks DB, Redis, and queue connectivity.

### `GET /v1/me`

Auth required. Returns user, tenant, role, and feature flags.

Current beta compatibility:

- `POST /api/auth/register`: disabled unless `VCB_ALT_USER_AUTH_ENABLED=true` and `VCB_ALT_USER_REGISTRATION_ENABLED=true`.
- `POST /api/auth/login`: returns an opaque bearer session token when local user auth is enabled.
- `GET /api/me`: bearer session required.

### `GET /v1/watchlist`

Auth required. Returns current user's watchlist. List endpoints should use input-based/keyset paging, not offset paging.

Supported query shape:

```text
?limit=25&after=<cursor>
?limit=25&before=<cursor>
```

Response list shape:

```json
{
  "items": [],
  "count": 0,
  "page": {
    "limit": 25,
    "count": 0,
    "has_more": false,
    "next_after": null,
    "previous_before": null,
    "sort": "ticker",
    "direction": "next"
  }
}
```

Offset-style inputs such as `offset=1000` are intentionally unsupported because they perform poorly on large tables and can duplicate or skip rows when records change during paging. See `plan.md` for Feature 00 implementation details.

Current beta compatibility:

- `GET /api/user/watchlist`: bearer session required, scoped by `tenant_id` and `user_id`.
- `POST /api/user/watchlist`: bearer session required.
- `DELETE /api/user/watchlist?ticker=<ticker>`: bearer session required.

### `POST /v1/watchlist`

Auth required.

```json
{"ticker": "PLTR", "archetype_hint": "A_AI_TECH", "notes": "optional"}
```

Requires idempotency key.

### `DELETE /v1/watchlist/{ticker}`

Auth required. Deletes current user's watchlist item.

### `POST /v1/evaluations`

Auth required.

```json
{"ticker": "PLTR", "mode": "cached_or_queue"}
```

Returns `200` with evaluation when cached data is fresh, or `202` with job ID.

### `GET /v1/evaluations/latest`

Auth required. Returns latest evaluations for current user's watchlist.

Evaluation output should include:

- `scoring_version`: deterministic version label for score reproducibility.
- `status`: internal audit/debug status.
- `decision_label`: private-beta/operator label.
- `public_label`: SaaS-safe user-facing label that avoids direct trade-action wording.

### `GET /v1/tickers/{ticker}/analysis`

Auth required. Returns the detail-page payload for a ticker:

- `evaluation`: current score, public label, rationale, warnings, and scoring version.
- `profile`: company name, sector, industry, and profile source.
- `history`: five-year daily chart points where supported, with `is_realtime` and freshness labels.
- `metrics`: current trend, surge, relative strength, drawdown, and moving-average-derived metrics.
- `expert_consensus`: concise review sections agreed by product, quant, risk, data, and compliance roles.

Current beta compatibility:

- `GET /api/ticker-analysis?ticker=<ticker>` returns the same shape for the token-protected dashboard.

### `GET /v1/jobs/{id}`

Auth required. Returns job status only if job belongs to current tenant/user or admin role.

### `POST /v1/exports`

Auth required. Creates a data export job.

### `DELETE /v1/account`

Auth required. Requires re-authentication and confirmation phrase.

## 4. Rate Limits

Initial limits:

- Login attempts: 5 per IP per 15 minutes
- Add watchlist: 60 per user per hour
- On-demand evaluation: 120 per user per day
- Export: 3 per user per day
- Account delete: 3 attempts per day
- Admin endpoints: stricter IP allowlist where possible

## 5. Idempotency

Required for:

- `POST /v1/watchlist`
- `POST /v1/evaluations`
- `POST /v1/exports`
- `DELETE /v1/account`

Store key by `(tenant_id, user_id, method, path, idempotency_key)`.

## 6. Current Beta Compatibility Endpoints

The current stdlib web deployment is not the future `/v1` SaaS API, but it now exposes safety endpoints that should be preserved or mapped during migration:

- `GET /api/provider-status`: token required in public mode. Returns configured provider, capability flags, timeout, cache TTL, and warnings without secrets.
- `GET /api/saas-readiness`: token required in public mode. Returns current 1000-user blockers.
- `GET /terms`, `GET /privacy`, `GET /risk-disclosure`: starter public-beta documents pending legal review.

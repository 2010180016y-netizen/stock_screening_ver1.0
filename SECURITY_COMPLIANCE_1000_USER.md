# Security And Compliance Plan For 1000 Users

Last updated: 2026-05-16

## 1. Hard Release Blockers

- No public launch without authentication.
- No public launch without tenant isolation tests.
- No public launch without legal review of investment-advice language.
- No public launch with automatic trading.
- No public launch with live provider keys in source or local `.env` on a shared server.

## 2. Authentication

- Use managed auth or battle-tested auth library.
- Require verified email.
- Support MFA for admin roles.
- Session cookies must be `HttpOnly`, `Secure`, `SameSite=Lax` or stricter.
- Rotate session secrets.

## 3. Authorization

- Enforce role checks in API middleware.
- Every user-owned query must scope by `tenant_id`.
- Admin actions require admin role and audit event.
- Support suspended/deleted user states.

## 4. Privacy

Collected data should be minimal:

- Email
- Watchlist tickers
- User settings
- Evaluation history
- Support/audit events

Avoid collecting:

- Brokerage credentials
- Account balances
- Tax IDs
- Full IP addresses in long-term logs

## 5. Financial/Legal Risk

Required product language:

- Decision support only.
- Not investment advice.
- No guaranteed return.
- User is responsible for final trade decision.
- No broker order placement.

Before public beta:

- Terms of service.
- Privacy policy.
- Risk disclaimer.
- Jurisdiction review for Korea/US users.

## 6. Logging

Must log:

- Request ID
- User/tenant IDs, not email, in normal logs
- Endpoint/action
- Status code
- Latency
- Provider failures
- Job failures

Must not log:

- API keys
- Passwords/tokens
- Full provider raw payloads containing licensed data unless permitted
- Sensitive user notes without explicit redaction policy

## 7. Abuse Controls

- Per-user and per-IP rate limiting.
- Provider budget limits.
- Watchlist size limits by plan.
- Job queue quotas per user/tenant.
- CAPTCHA or equivalent on signup/login if abused.

## 8. Security Testing

Minimum tests:

- User A cannot read User B watchlist.
- User A cannot read User B evaluations.
- Non-admin cannot access admin endpoints.
- Deleted user cannot authenticate.
- Suspended user cannot enqueue jobs.
- Rate limit returns `429`.
- Logs redact secrets.
- CSRF test for state-changing browser requests.


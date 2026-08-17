# OAuth, MFA, And RBAC Plan

Last updated: 2026-05-22 KST

## Current State

- Local password/session auth exists.
- Production SaaS mode can register/login users and isolate tenant watchlists/jobs.
- User roles exist as `owner`, `admin`, and `member`, but no production-grade RBAC matrix is enforced across admin features yet.
- `require_role(user, allowed_roles)` now exists as the code-level RBAC guard helper.
- OAuth, email verification, MFA, password reset, account lockout, and admin session step-up are not implemented.

## Launch Requirement

VCB-Alt must not open unrestricted public signup until these controls are implemented and tested:

- OAuth or verified-email auth provider.
- MFA for owners/admins.
- RBAC checks on all admin, operations, export, delete, and worker-management actions.
- Account recovery and session revocation.
- Audit log for login, logout, role changes, export, delete, queue worker trigger, and provider configuration changes.

## RBAC Matrix

| Action | Owner | Admin | Member | Anonymous |
|---|---:|---:|---:|---:|
| Register tenant | yes | no | no | yes, if public registration enabled |
| Login/logout | yes | yes | yes | no |
| Manage own watchlist | yes | yes | yes | no |
| Queue own scan | yes | yes | yes | no |
| View own scan jobs | yes | yes | yes | no |
| Export tenant data | yes | yes | no | no |
| Delete tenant/user data | yes | no | no | no |
| View tenant users | yes | yes | no | no |
| Change roles | yes | no | no | no |
| Trigger worker/admin ops | yes with MFA | yes with MFA | no | no |
| Change provider credentials | yes with MFA | no | no | no |

## Implementation Steps

1. Add auth provider selection:
   - `VCB_ALT_AUTH_PROVIDER=local|oauth`.
   - Keep `local` for development only.
   - Use OAuth/OIDC for public signup.

2. Add verified-email gate:
   - Block scans until email is verified.
   - Store `email_verified_at`.

3. Add MFA fields:
   - `mfa_enabled`.
   - `mfa_verified_at`.
   - `last_step_up_at`.

4. Add RBAC helpers:
   - `require_role(user, allowed_roles)`. Status: helper implemented.
   - `require_step_up(user)` for owner/admin sensitive actions.

5. Add audit events:
   - `audit_events(id, tenant_id, actor_user_id, action, target_type, target_id, metadata_json, created_at)`.

6. Add tests:
   - Member cannot export/delete tenant data.
   - Admin cannot change owner role.
   - Owner sensitive action requires MFA step-up.
   - Anonymous cannot access tenant data.
   - Expired/revoked sessions fail.

## Current Release Decision

Status: not complete.

The current build is acceptable for controlled private beta. It is not acceptable for unrestricted public SaaS until this plan is implemented and independently tested.

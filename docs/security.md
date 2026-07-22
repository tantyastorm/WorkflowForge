# Security

This document records the planned WorkflowForge security foundation for Phase 2. It is architectural documentation, not an implementation record.

## Security Principles

- Keep secrets out of source control, logs, JWTs, and audit metadata.
- Use short-lived access credentials and server-side revocation.
- Treat tenant boundaries as authorization boundaries.
- Keep transport-level concerns in app composition roots.
- Keep cryptography and persistence behind adapters.
- Prefer explicit application policies over implicit global state.

## Access And Refresh Transport

Access tokens are short-lived JWTs sent with:

```http
Authorization: Bearer <access-token>
```

For the React web application, refresh tokens are opaque rotating tokens sent through an HttpOnly cookie. The frontend keeps the access token in memory rather than `localStorage` or other JavaScript-readable persistent storage.

Access JWTs are signed with HS256 using `WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET`.
The default access-token lifetime is 15 minutes. The JWT contains only `sub`,
`sid`, `jti`, `iat`, `exp`, `iss`, and `aud`; tenant, role, permission,
password, and refresh-token state are excluded.

For Phase 2 tenant-scoped API routes, the selected organization is the
`organization_id` route parameter under `/api/v1/organizations/{organization_id}`.
The API rejects malformed UUID route parameters through the standard validation
envelope and returns a generic tenant-access denial for missing, inactive, or
unusable membership. Permission denial remains a separate `403` response so
authentication, tenant access, and authorization failures stay distinguishable
inside the application boundary.

Refresh-cookie endpoints must use:

- `HttpOnly`.
- `Secure` in production.
- `SameSite=Lax` by default.
- Restricted cookie path.
- Origin validation.
- CSRF protection for cookie-authenticated state-changing endpoints.

The API exposes authentication under `/api/v1/auth`. Login returns the access
token in JSON and sets the raw refresh token only in an HttpOnly cookie. Refresh,
logout, and logout-all require a readable CSRF cookie to match the configured
CSRF request header using constant-time comparison. Refresh rotates both the
refresh cookie and CSRF cookie after successful durable rotation. Invalid or
replayed refresh attempts return a generic authentication failure and clear auth
cookies.

Cookie-authenticated state-changing requests reject explicitly untrusted or
malformed `Origin` values by exact scheme, host, and port comparison against the
configured CORS origins. Requests without an `Origin` header are allowed for
non-browser clients. Login does not require a pre-existing CSRF cookie, but an
explicit untrusted login `Origin` is rejected.

## Refresh-Token Storage

Refresh tokens are cryptographically random opaque values. Only the SHA-256
digest is persisted. Raw refresh tokens, access tokens, password material, API
keys, provider credentials, and session secrets must not be logged or written to
audit metadata.

Refresh-token digesting is separate from password hashing. Passwords use Argon2id;
server-generated high-entropy refresh tokens use deterministic SHA-256 digests
so they can be looked up and compared. Comparison in application code uses
constant-time digest comparison.

Refresh rotation is atomic at the repository boundary. Rotation consumes the
expected current token digest and generation, records replacement lineage, and
inserts the next token generation in one transaction. Stale, revoked, expired,
or already-used rotation attempts fail with a stable conflict and preserve
replay-detection evidence. Logout of one session and logout-all revoke current
refresh credentials without involving tenant context.

The refresh use case responds to replay of an already-used token by revoking the
affected session and its current refresh credentials. Access-token verification
checks durable session state after JWT verification, so revoked sessions stop
new authenticated requests before access-token expiry.

Session lifecycle use cases own explicit transaction boundaries through an
application `TransactionManager` port. Login returns tokens only after the
session and initial refresh-token record are committed. Normal refresh returns a
new token pair only after the replacement generation is committed. Replay
detection is intentionally durable before the security error is returned:
revocation is committed, then `RefreshTokenReplayError` is raised.

## Password Security

Passwords use Argon2id through an infrastructure adapter with a minimum length of
12 and maximum length of 256 enforced by application password-setting behavior.
Passphrases and password managers are allowed. Arbitrary complexity rules are
not required. Stored hashes include the salt, algorithm, and parameters in the
library-managed hash format and can support future parameter rehashing.

Plaintext passwords are accepted only at application use-case boundaries and are
hashed before persistence. Password hashes are stored in the separate
`password_credentials` table rather than on the durable user identity record.
Authentication uses generic invalid-credential behavior for unknown emails,
missing credentials, and incorrect passwords, and performs dummy verification for
missing-account paths where possible. Disabled users are rejected and no session
or token is issued by the password authentication use case.

## Rate Limiting

WorkflowForge plans Redis-backed rate limiting for:

- Login.
- Registration.
- Refresh.
- Membership invitations.

PostgreSQL remains the source of truth for users, sessions, memberships, and refresh-token records. Redis stores rate-limit counters and transient coordination only.

## HTTP Error Policy

Authentication and authorization errors use consistent status codes:

- `401` for missing or invalid authentication.
- `403` for authenticated users lacking permission on visible tenant resources.
- `404` for cross-tenant resources whose existence must remain hidden.
- `409` for invariant and uniqueness conflicts.
- `422` for validation errors.
- `429` for rate limiting.

Responses should avoid revealing whether hidden tenant resources exist.

## Local Development

Local development may enable registration with `WORKFLOWFORGE_AUTH_REGISTRATION_ENABLED`. Production defaults registration to disabled and uses a future CLI bootstrap command for initial setup. WorkflowForge must not provide default admin credentials.

## Architecture Boundaries

Security domain rules belong in `packages/domain` when they are product invariants. Security policies, authentication use cases, authorization checks, and security ports belong in `packages/application` or `packages/contracts` as appropriate. Cryptography, token signing, digesting, persistence, and Redis-backed rate-limiting adapters belong in `packages/infrastructure`. HTTP headers, cookies, CSRF validation, Origin validation, and dependency composition belong in `apps/api`. Frontend token handling and organization UX belong in `apps/web`.

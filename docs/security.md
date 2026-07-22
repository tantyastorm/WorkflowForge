# Security

This document records the WorkflowForge security foundation for Phase 2.

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

WorkflowForge uses Redis-backed fixed-window rate limiting for authentication
endpoints:

- Login is limited by normalized email identifier and client address before
  password verification.
- Refresh is limited by client address before refresh-token lookup.

Counters are keyed with SHA-256 digests and never include raw email addresses or
raw client addresses. Counter increments and expiry assignment run through one
Redis Lua script so a failed process cannot leave a new counter without a TTL.
Successful login and refresh clear the corresponding failure counters.

Development defaults to fail-open behavior when Redis is unavailable so local
work is not blocked by transient infrastructure failures. Production settings
must use fail-closed rate limiting. Rate-limited and fail-closed backend
failures return `429` with `Retry-After` and emit audit events.

PostgreSQL remains the source of truth for users, sessions, memberships, and
refresh-token records. Redis stores rate-limit counters and transient
coordination only.

## Session Cleanup

Expired refresh-token rows and old inactive sessions are cleaned by the
`security.sessions.cleanup` Celery task. The task is registered on workers by
default. Celery Beat schedules it only when
`WORKFLOWFORGE_CLEANUP_SCHEDULE_ENABLED=true`.

Cleanup runs in bounded batches, deletes expired refresh tokens first, deletes
expired sessions after the configured expired-session retention, and deletes
revoked sessions after the configured revoked-session retention. Audit rows
preserve nullable session references through database constraints rather than
blocking cleanup.

## HTTP Security Headers

API responses include:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `X-Frame-Options: DENY`

Production responses also include
`Strict-Transport-Security: max-age=31536000; includeSubDomains`.

## HTTP Error Policy

Authentication and authorization errors use consistent status codes:

- `401` for missing or invalid authentication.
- `403` for authenticated users lacking permission on visible tenant resources.
- `404` for cross-tenant resources whose existence must remain hidden.
- `409` for invariant and uniqueness conflicts.
- `422` for validation errors.
- `429` for rate limiting.

Responses should avoid revealing whether hidden tenant resources exist.

## Security Audit Trail

Phase 2 records durable structured audit events for identity, authentication,
session, tenancy, and authorization activity in PostgreSQL. Successful
security-state changes are audited in the same transaction as the state change.
Failures and denials that return `401` or `403` use a dedicated audit
transaction so incident-review evidence survives the failed request.
If independent audit persistence fails, the failure is logged with request
correlation context and the original public `401` or `403` response is
preserved. Same-transaction audit persistence failures roll back the owning
security-state change.

Audit metadata excludes plaintext passwords, password hashes, raw access or
refresh tokens, refresh digests, signing secrets, cookies, CSRF values,
authorization headers, request bodies, and raw exception reprs. Direct source IP
and bounded user agent are allowed but treated as security-sensitive metadata.
Audit dashboards, public audit endpoints, SIEM export, alerting, retention jobs,
partitioning, and archival are deferred.

## Local Development

WorkflowForge does not expose public registration in Phase 2 and must not ship
default admin credentials. Initial setup uses the CLI command:

```shell
workflowforge-bootstrap-owner --email owner@example.com --display-name "Owner" --organization-name "Example" --organization-slug example --password-from-env
```

The command reads `WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD` only when
`--password-from-env` is supplied; otherwise it prompts with hidden input and
confirmation. The password is never accepted as a positional command-line
argument and is not printed.

Bootstrap takes a transaction-scoped PostgreSQL advisory lock, then refuses if
any user or organization already exists. A successful bootstrap creates the
first active owner, organization, membership, password credential, and audit row
in one transaction. A refused bootstrap records `bootstrap.refused` and exits
without creating identity state.

Production configuration is intentionally strict: debug mode must be disabled,
the JWT signing secret must differ from the development default, refresh cookies
must be Secure, PostgreSQL and Redis passwords must be configured, rate limiting
must fail closed, access tokens may not exceed one hour, and sessions may not
exceed 90 days.

## Architecture Boundaries

Security domain rules belong in `packages/domain` when they are product invariants. Security policies, authentication use cases, authorization checks, and security ports belong in `packages/application` or `packages/contracts` as appropriate. Cryptography, token signing, digesting, persistence, and Redis-backed rate-limiting adapters belong in `packages/infrastructure`. HTTP headers, cookies, CSRF validation, Origin validation, and dependency composition belong in `apps/api`. Frontend token handling and organization UX belong in `apps/web`.

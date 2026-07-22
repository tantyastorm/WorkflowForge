# Identity

This document records the planned WorkflowForge identity foundation for Phase 2. It is architectural documentation, not an implementation record.

## Goals

- Support the React operator console without storing long-lived bearer credentials in browser storage.
- Keep room for future CLI clients, Telegram account linking, and API keys.
- Allow server-side session revocation, logout, logout-all, and refresh-token reuse detection.
- Keep authentication transport separate from tenancy, authorization, and audit behavior.
- Preserve the existing modular-monolith package boundaries.

## Authentication Model

WorkflowForge will use a hybrid token model:

- Short-lived JWT access tokens.
- HS256 signing with a configured secret.
- 15-minute access-token lifetime by default.
- Access tokens transported through `Authorization: Bearer`.
- Opaque rotating refresh tokens transported through an HttpOnly cookie for the React web application.
- 30-day refresh-token and session lifetimes by default.
- Durable server-side session records and refresh-token records.
- Refresh-token reuse detection.
- Token-family revocation.
- Logout and logout-all.

Access JWTs must use minimal claims:

- `sub`
- `sid`
- `jti`
- `iat`
- `exp`
- `iss`
- `aud`

Access JWTs must not contain organization IDs, roles, permission matrices, email addresses, secrets, refresh-token material, or provider credentials. The API resolves organization membership and permissions server-side for each tenant-scoped request.

This model supports the React application by keeping the refresh credential in an HttpOnly cookie while the frontend keeps the access token in memory. It supports a future CLI because non-browser clients can use bearer access tokens and an appropriate refresh flow without depending on browser cookies. It supports future Telegram linking because sessions and linked identities can be represented server-side without embedding provider state in access tokens. It supports future API keys because API-key authentication can resolve to the same server-side user or actor context without changing tenant authorization. It supports local development because JWT validation, refresh rotation, and session revocation can run against the local PostgreSQL and Redis stack. It supports server-side revocation because sessions and refresh-token families are durable records.

## Password Model

WorkflowForge passwords use:

- Argon2id password hashing.
- Minimum length of 12 characters.
- Maximum length of 256 characters.
- Support for passphrases and password managers.
- No arbitrary composition rules such as mandatory symbols, numbers, or uppercase letters.
- Future parameter rehashing when stored hash parameters become outdated.
- No plaintext password logging.

Validation errors describe length constraints without echoing password material. Password
hashes, hash parameters, and future rehash decisions belong behind infrastructure
cryptography adapters and application use cases, not HTTP routes.

Password credentials are stored separately from the `users` table in
`password_credentials`. The table has one row per user, keyed by `user_id`, and
is reached only through the password credential repository boundary. Normal
user lookups return display identity, lifecycle state, and timestamps only; they
do not return password hashes.

Email/password authentication normalizes email with the same identity value
object used by user persistence. Unknown users, missing credentials, malformed
stored credentials, and wrong passwords fail with the same generic invalid
credential behavior. Disabled users do not authenticate even when the supplied
password is correct. Authentication returns only a safe principal; session,
refresh-token, tenant-context, and permission resolution remain separate steps.

## Email Normalization

Email addresses are normalized with:

```python
email.strip().casefold()
```

WorkflowForge will persist both the display or original email and the normalized email. Uniqueness is based on normalized email.

Provider-specific transformations, including Gmail dot removal or plus-address rewriting, are intentionally not used. Those transformations are provider-specific, surprising across domains, and can merge addresses that the owning provider or organization treats as distinct.

## Session And Refresh Tokens

Refresh tokens are cryptographically random opaque values. The raw token is returned only to the client through the appropriate cookie flow and is never persisted.

WorkflowForge persists tenant-independent authenticated sessions in
`auth_sessions`. A user may have multiple sessions, and each session has
creation, update, expiry, and revocation timestamps. Deleting a user cascades to
sessions and refresh-token records so hard-deleted identities do not leave
orphaned authentication material.

Persisted refresh-token records live in `refresh_tokens` and store:

- SHA-256 digest of the token.
- Session ID.
- Token family ID.
- Generation number.
- Issued timestamp.
- Expiry timestamp.
- Used timestamp.
- Revoked timestamp.
- Replaced-by token reference.

Refresh rotation is represented by consuming the current generation and inserting
the replacement generation in one repository operation. The old record receives
`used_at` and `replaced_by_token_id`, while the new record keeps the same token
family and advances generation by one. Reuse of an already-used, revoked,
expired, or superseded refresh token can be detected because the digest remains
durable as a non-current lineage record. The application refresh use case treats
already-used or replaced refresh tokens as replay and revokes the affected
session and its current refresh credentials. Another session for the same user is
not revoked by that replay response.

Access-token verification validates the JWT signature and required claims, then
checks durable session state. Revoked, expired, missing, or user-mismatched
sessions reject the token without resolving tenant membership or permissions.

The HTTP API exposes session lifecycle behavior through `/api/v1/auth/login`,
`/api/v1/auth/refresh`, `/api/v1/auth/logout`, `/api/v1/auth/logout-all`, and
`/api/v1/auth/me`. Access tokens use `Authorization: Bearer`. Refresh tokens are
cookie-only and are not present in request or response JSON. The `/me` response
returns only user ID, session ID, issue time, and expiry time; tenant context,
roles, and permissions remain separate.

Authentication, refresh, replay, logout, logout-all, and password credential
changes emit durable structured audit events. Audit events may include actor
user ID and session ID where known, but they never include plaintext passwords,
password hashes, raw access tokens, raw refresh tokens, refresh digests, cookies,
CSRF values, or authorization headers.

Tenant-scoped HTTP routes resolve organization context from the route parameter
and durable membership state after bearer authentication succeeds. `/auth/me`
remains authentication-only and does not require or return tenant selection.

## Registration And Bootstrap

Registration is controlled by `WORKFLOWFORGE_AUTH_REGISTRATION_ENABLED`.

Development registration may be enabled. Production registration defaults to disabled. Registration creates a user only; organization creation is a separate operation. The creator of an organization becomes its owner.

WorkflowForge will not ship default admin credentials. A CLI bootstrap command for initial production setup is planned later in Phase 2.

## HTTP Authentication Errors

- `401` is used for missing or invalid authentication.
- `403` is used for authenticated users who lack permission on a visible tenant resource.
- `404` is used for cross-tenant resources whose existence must remain hidden.
- `409` is used for invariant and uniqueness conflicts.
- `422` is used for validation errors.
- `429` is used for rate limiting.

## Architecture Boundaries

Identity domain rules belong in `packages/domain` where they are durable business concepts. Session use cases, password policy decisions, refresh-token rotation, and authentication ports belong in `packages/application` or `packages/contracts` as appropriate. Password hashing, token signing, token digesting, Redis rate limiting, and persistence adapters belong in `packages/infrastructure`. HTTP cookie handling, bearer-token parsing, response mapping, and dependency composition belong in `apps/api`. Frontend authentication state and login/logout UX belong in `apps/web`.

WorkflowForge should not create a generic `AuthService` that owns identity, sessions, tenancy, authorization, and audit together.

## Persistence Foundation

Phase 2 persists users with display email, normalized email, display name, active state, and lifecycle timestamps. Normalized email remains the uniqueness key and uses the same `email.strip().casefold()` behavior as the domain value object.

Registration routes, password reset, tenant selection, and frontend
authentication UX remain outside this step.

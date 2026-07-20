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

Refresh-cookie endpoints must use:

- `HttpOnly`.
- `Secure` in production.
- `SameSite=Lax` by default.
- Restricted cookie path.
- Origin validation.
- CSRF protection for cookie-authenticated state-changing endpoints.

## Refresh-Token Storage

Refresh tokens are cryptographically random opaque values. Only the SHA-256 digest is persisted. Raw refresh tokens, access tokens, password material, API keys, provider credentials, and session secrets must not be logged or written to audit metadata.

Refresh rotation must be atomic and must support reuse detection and token-family revocation.

## Password Security

Passwords use Argon2id with a minimum length of 12 and maximum length of 256. Passphrases and password managers are allowed. Arbitrary complexity rules are not required. Stored hashes should support future parameter rehashing.

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

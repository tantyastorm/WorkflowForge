# ADR 0002: Authentication and session model

- Status: Accepted
- Date: 2026-07-20

## Context

WorkflowForge needs authentication for the React operator console and future non-browser clients. The system also needs server-side revocation, logout, logout-all, refresh-token reuse detection, and a path toward future Telegram linking and API keys.

The Phase 1 architecture is a modular monolith with PostgreSQL as durable state, Redis for transient coordination, and app composition roots around internal package boundaries.

## Decision

WorkflowForge will use short-lived JWT access tokens transported through `Authorization: Bearer` and opaque rotating refresh tokens transported through an HttpOnly cookie for the React web application.

The backend will persist durable server-side session and refresh-token records. Refresh-token rotation is atomic, reuse detection revokes the token family, and logout or logout-all can revoke sessions and token families server-side.

Access JWTs contain only `sub`, `sid`, `jti`, `iat`, `exp`, `iss`, and `aud`. They do not contain organization IDs, roles, permission matrices, email addresses, secrets, or token material.

The initial implementation signs access JWTs with HS256 using a configured secret
that must be replaced outside local development. Access tokens live for 15
minutes. Refresh tokens and sessions live for 30 days by default, and refresh
token lifetime does not exceed session lifetime.

Passwords use Argon2id, minimum length 12, maximum length 256, support passphrases and password managers, avoid arbitrary complexity requirements, support future parameter rehashing, and must never be logged in plaintext.

Emails are normalized with `email.strip().casefold()`. WorkflowForge persists both display or original email and normalized email, with uniqueness based on normalized email. Provider-specific transformations such as Gmail dot removal are not used.

Public registration is not exposed in Phase 2. No default admin credentials are
provided. Initial setup uses a first-owner bootstrap CLI that creates the first
user, organization, owner membership, password credential, and audit row in one
transaction, and refuses to run after users or organizations exist.

## Alternatives considered

Pure server-side session cookies were considered. They simplify browser authentication but fit CLI clients, API clients, and future non-browser integrations less naturally.

Long-lived JWTs were considered. They reduce refresh complexity but weaken revocation and make stolen tokens useful for too long.

Refresh tokens in JavaScript storage were considered. They are easy for a single-page app to call with, but increase exposure to XSS and persistent browser compromise.

Opaque access tokens were considered. They support immediate introspection and revocation, but require a server-side lookup for every authenticated request and add coupling before access-token needs require it.

## Consequences

The React app can keep access tokens in memory while relying on HttpOnly refresh cookies. Future CLI clients can use bearer access tokens and a suitable refresh flow. Future Telegram linking and API keys can resolve to durable server-side actors without changing the tenant authorization model.

The system must implement token signing, refresh-token digesting, session persistence, refresh rotation, reuse detection, and revocation carefully. Authentication is more complex than a single cookie or a long-lived JWT.

## Security implications

Refresh-cookie endpoints must use HttpOnly cookies, `Secure` in production, `SameSite=Lax` by default, restricted cookie paths, Origin validation, and CSRF protection for cookie-authenticated state-changing endpoints.

Refresh tokens are cryptographically random opaque values. Only SHA-256 token digests are persisted. Access tokens, refresh tokens, password material, API keys, provider credentials, and secrets must not be logged or placed in audit metadata.

Access-token verification checks both JWT claims and durable session state.
Revoked, expired, missing, or user-mismatched sessions reject otherwise valid
access tokens so logout takes effect before access-token expiry.

Redis-backed rate limiting protects login and refresh. PostgreSQL remains the
source of truth for users, sessions, and refresh-token records.

## Future migration path

Opaque access tokens can be introduced later if immediate access-token introspection becomes necessary. WebAuthn, SSO, device-code login, Telegram linking, and API keys can be added as additional credential or actor-resolution mechanisms that feed the same server-side session and authorization model.

The bootstrap command can initialize production without opening public
registration. WebAuthn, SSO, password reset, MFA, device-code login, Telegram
linking, and API keys remain future credential paths.

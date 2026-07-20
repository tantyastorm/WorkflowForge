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

Passwords use Argon2id, minimum length 12, maximum length 256, support passphrases and password managers, avoid arbitrary complexity requirements, support future parameter rehashing, and must never be logged in plaintext.

Emails are normalized with `email.strip().casefold()`. WorkflowForge persists both display or original email and normalized email, with uniqueness based on normalized email. Provider-specific transformations such as Gmail dot removal are not used.

Registration is controlled by `WORKFLOWFORGE_AUTH_REGISTRATION_ENABLED`. Development registration may be enabled; production registration defaults to disabled. Registration creates a user. Organization creation is separate, and the organization creator becomes owner. No default admin credentials are provided. A CLI bootstrap command is planned later in Phase 2.

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

Redis-backed rate limiting is planned for login, registration, and refresh. PostgreSQL remains the source of truth for users, sessions, and refresh-token records.

## Future migration path

Opaque access tokens can be introduced later if immediate access-token introspection becomes necessary. WebAuthn, SSO, device-code login, Telegram linking, and API keys can be added as additional credential or actor-resolution mechanisms that feed the same server-side session and authorization model.

Registration can remain disabled in production while the planned CLI bootstrap command creates the first user and organization.

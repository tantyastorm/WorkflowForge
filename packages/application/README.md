# Application Package

Belongs here: use cases, orchestration, ports, command handling, workflow coordination, and application-level policies.

Does not belong here: framework entry points, database implementations, external service clients, frontend code, or provider-specific adapters.

Owner: application layer.

Dependency direction: may depend on `packages/domain` and `packages/contracts`. It must not depend directly on `packages/infrastructure`.

Python workspace distribution: `workflowforge-application`.

## Document Services

The document application foundation defines a `DocumentRepository` port and a focused `DocumentService`.

Current use cases:

- Register document metadata.
- Retrieve document metadata by ID.

Registration is idempotent by content hash for the current non-tenant model. Re-registering identical content returns the existing document metadata. Infrastructure still enforces a database uniqueness constraint so concurrent duplicate inserts converge safely.

The application layer does not write file bytes, call object storage, expose HTTP schemas, or depend on SQLAlchemy.

## Authorization

The authorization foundation defines immutable tenant context, transport-neutral authorization errors, permission checks, and pure membership-administration target policies.

Current concepts:

- `TenantContext`: trusted application context with user, organization, membership, role, and resolved permissions.
- `AuthorizationPolicy`: side-effect-free permission checks over `TenantContext`.
- `MembershipAdministrationPolicy`: owner/admin target restrictions for membership management.
- `PermissionDenied`, `TenantBoundaryViolation`, and `MembershipAdministrationDenied`: transport-neutral errors for future API mapping.

This package does not resolve tenant context from HTTP requests, query persistence, authenticate users, issue tokens, write audit records, or expose API schemas.

## Identity Repository Ports

The identity application boundary defines repository ports for users, organizations, and memberships. Ports use domain entities and value objects only; SQLAlchemy models remain infrastructure details.

The ports are intentionally focused on current identity persistence needs rather than a generic base repository. Membership lookups that target tenant-owned membership state include organization identity to make cross-tenant access harder to express accidentally.

## Password Authentication

The identity application boundary also defines `PasswordHasher` and
`PasswordCredentialRepository` ports, plus focused `AuthenticateUser` and
`SetUserPassword` use cases. Plaintext passwords enter only through those use
case inputs. Password setting hashes before persistence, while authentication
returns a safe user principal without password hashes, tokens, sessions,
organization selection, or permissions.

Invalid email/password combinations, unknown users, and missing credentials use
generic invalid-credential behavior. Disabled users are rejected by the
authentication use case and do not receive an authenticated result.

## Sessions

The identity application boundary defines a `SessionRepository` port for durable
authenticated sessions and refresh-token lineage. Sessions are tenant-independent
and can be looked up, revoked individually, revoked in bulk for logout-all, and
rotated with compare-and-swap semantics over the expected refresh-token digest
and generation.

The application boundary also defines a `RefreshTokenHasher` port. It is
separate from password hashing because high-entropy opaque refresh tokens are
stored as deterministic digests for lookup and replay detection.

Session lifecycle use cases include `StartUserSession`, `RefreshSession`,
`LogoutSession`, `LogoutAllSessions`, and `VerifyAccessToken`. They depend on
ports for access-token encoding, refresh-token generation, refresh-token
digesting, time, ID generation, and session persistence. They return safe token
or principal contracts and do not expose password hashes, refresh-token digests,
tenant context, roles, or permissions.

State-changing session lifecycle use cases also depend on the narrow
`TransactionManager` port. Login commits only after authentication, token
issuance, and session persistence succeed; failures roll back and return no
token pair. Refresh commits only after compare-and-swap rotation succeeds. If an
already-used or superseded refresh token is replayed, the refresh use case
revokes the affected session and current refresh credential, commits that
revocation, and then raises `RefreshTokenReplayError` so replay evidence cannot
be lost by normal exception rollback. Logout and logout-all commit successful
revocations and roll back failures.

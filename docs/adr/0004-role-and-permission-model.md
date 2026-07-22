# ADR 0004: Role and permission model

- Status: Accepted
- Date: 2026-07-20

## Context

WorkflowForge needs organization authorization for identity, membership management, audit access, security administration, API keys, provider credentials, and future operational workflow behavior.

Authorization must remain server-side, reviewable, testable, and independent from JWT claims.

## Decision

WorkflowForge will use code-defined roles and permissions. Membership stores the selected role. The permission map is defined in application code and resolved into `TenantContext`.

Roles:

- `owner`
- `admin`
- `operator`
- `reviewer`
- `auditor`

Permissions:

- `organization.read`
- `organization.update`
- `membership.read`
- `membership.invite`
- `membership.update`
- `membership.remove`
- `audit.read`
- `security.manage`
- `api_keys.manage`
- `provider_credentials.manage`

Owner has full organization authority. Admin cannot create, promote, demote, suspend, update, or remove owners. Operator has future operational permissions but no security management. Reviewer has limited future review access. Auditor has read-only audit and operational access.

The last active owner cannot be removed, suspended, or demoted.

## Alternatives considered

Permissions embedded in JWTs were considered. They are rejected because role and permission changes would not take effect until token expiry and because JWTs would grow into authorization state.

Database-stored arbitrary permission matrices were considered. They provide flexibility but add complexity before WorkflowForge has product behavior requiring custom roles.

A single admin/member split was considered. It is too coarse for audit, review, operations, provider credentials, API keys, and owner-protection rules.

External policy engines were considered. They are powerful but add operational and conceptual weight before the authorization model has stabilized.

## Consequences

Authorization behavior is versioned with code and easy to test. Membership rows stay small because they store role selection rather than a permission matrix.

Changing permissions requires a code change and deployment. Custom organization roles are deferred.

## Security implications

Owner protection is an invariant, not just a permission mapping. Admins cannot mutate owners even if they have membership permissions. The last active owner cannot be removed, suspended, or demoted.

JWTs contain no roles, permissions, organization IDs, or authorization matrices. The backend resolves permissions server-side for each tenant context.

## Future migration path

Custom roles can be introduced later by adding role definitions or organization-specific permission sets while preserving the same permission names and policy checks.

External policy engines can be evaluated later if authorization becomes too complex for code-defined policies.

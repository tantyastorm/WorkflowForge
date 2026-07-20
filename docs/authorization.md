# Authorization

This document records the planned WorkflowForge authorization foundation for Phase 2. It is architectural documentation, not an implementation record.

## Model

WorkflowForge uses organization membership roles with code-defined permissions. Membership stores the selected role. The permission mapping is defined in code so authorization behavior can be reviewed, tested, and versioned with application logic.

JWTs do not carry roles, permissions, organization IDs, or authorization matrices. Authorization is resolved server-side from the authenticated user, active organization, active membership, and code-defined permission map.

## Roles

- `owner`
- `admin`
- `operator`
- `reviewer`
- `auditor`

## Permissions

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

## Role Expectations

Owner has full organization authority.

Admin can manage most organization settings and memberships, but cannot create, promote, demote, suspend, update, or remove owners.

Operator has future operational permissions but no security management.

Reviewer has limited future review access.

Auditor has read-only audit and operational access.

The last active owner cannot be removed, suspended, or demoted.

## Initial Permission Mapping

The initial code-defined mapping should be conservative:

| Role | Permissions |
| --- | --- |
| `owner` | All organization permissions |
| `admin` | `organization.read`, `organization.update`, `membership.read`, `membership.invite`, `membership.update`, `membership.remove`, `audit.read`, `api_keys.manage`, `provider_credentials.manage` |
| `operator` | `organization.read`, `membership.read` plus future operational permissions |
| `reviewer` | `organization.read` plus future review permissions |
| `auditor` | `organization.read`, `membership.read`, `audit.read` plus future read-only operational permissions |

Admin permission checks must still enforce owner-protection invariants. Permission presence alone is not enough to mutate owner memberships.

## Policy Placement

Authorization policy code belongs near application use cases, not inside SQLAlchemy models or FastAPI route bodies. Routes resolve authentication and tenant context, then call application use cases. Use cases check permissions and enforce invariants before invoking repositories.

## HTTP Error Policy

- `401` means authentication is missing or invalid.
- `403` means the authenticated user lacks permission on a visible tenant resource.
- `404` hides cross-tenant resources when revealing existence would leak information.
- `409` covers invariants such as trying to remove the last active owner.
- `422` covers malformed or invalid request payloads.
- `429` covers rate limiting.

## Architecture Boundaries

Membership role invariants belong in `packages/domain`. Permission maps, policy checks, and authorization ports belong in `packages/application` or `packages/contracts` as appropriate. Persistence of memberships and tenant-scoped reads belongs in `packages/infrastructure`. HTTP dependency composition and error mapping belong in `apps/api`. Frontend affordances may hide unavailable actions, but backend authorization remains authoritative.

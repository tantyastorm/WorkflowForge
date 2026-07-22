# Tenancy

This document records the planned WorkflowForge tenancy foundation for Phase 2. It is architectural documentation, not an implementation record.

## Tenant Context Transport

Tenant-scoped API routes use organization route parameters:

```text
/api/v1/organizations/{organization_id}/...
```

The API must never trust organization IDs from arbitrary request bodies. Request bodies may identify tenant-owned resources only within the tenant context already established by the route and authenticated user.

Phase 2 resolves the route `organization_id` against current durable membership
state on every tenant-scoped request. WorkflowForge does not silently choose a
default organization and does not embed tenant IDs, roles, or permissions in
access tokens.

## TenantContext

Tenant-scoped application use cases receive an explicit tenant context:

```python
TenantContext(
    user_id,
    organization_id,
    membership_id,
    role,
    permissions,
)
```

The API resolves this context server-side from:

- Authenticated user.
- Active organization from the route parameter.
- Active membership.
- Code-defined permission map.

Application use cases should not infer the active organization from global state, request bodies, or frontend-provided roles.

## Isolation Strategy

Phase 2 tenant isolation uses:

- API tenant validation.
- Explicit `TenantContext` in application use cases.
- Tenant-scoped repository interfaces.
- Organization foreign keys on tenant-owned tables.
- Composite tenant-aware uniqueness constraints.
- Indexes beginning with `organization_id` where appropriate.

Repository interfaces for tenant-owned data should accept `organization_id` or `TenantContext` deliberately. Infrastructure query implementations must constrain tenant-owned reads and writes by organization.

Phase 2 persists organizations and memberships. Organization ownership is represented through owner memberships, not an `owner_user_id` shortcut on organizations. Membership repository operations that retrieve tenant-owned membership records include `organization_id` where appropriate.

## PostgreSQL RLS Deferral

PostgreSQL row-level security is deferred for Phase 2.

The initial system uses a single application database role. Enforcing RLS correctly with connection pools, transaction-local context, background workers, migrations, and operational scripts would add complexity before the tenant model has enough product behavior to prove its shape.

Strict repository enforcement is easier to review and test now. RLS may be introduced later as defense-in-depth once tenant tables, repository contracts, and operational patterns stabilize.

## Tenant-Aware Uniqueness

Tenant-owned uniqueness should be scoped with `organization_id` unless the business rule is intentionally global. Examples include future workflow names, provider credential labels, membership invite records, and user-visible resource identifiers.

Global uniqueness remains appropriate for normalized user email addresses and other identity records that represent a person or credential outside a specific organization.

## Cross-Tenant Errors

When a resource belongs to another organization and revealing its existence would leak tenant information, the API returns `404`. When the tenant resource is visible but the authenticated user lacks a permission on it, the API returns `403`.

Tenant-context resolution returns a generic `403` when the selected organization
does not exist, is inactive, lacks a usable membership for the authenticated
user, or the membership is invited, suspended, or removed. The application keeps
the internal distinction in transport-neutral authorization errors for future
audit logging, while public HTTP responses avoid unnecessary organization and
membership enumeration.

The initial HTTP proof endpoints are:

- `GET /api/v1/organizations/{organization_id}/tenancy/context`
- `GET /api/v1/organizations/{organization_id}/tenancy/authorized-probe`

They exist to validate tenant-context and permission dependency composition and
do not implement organization switching, membership administration, dashboards,
or document access.

## Architecture Boundaries

Tenant membership rules belong in `packages/domain`. Tenant context resolution, authorization policy invocation, and tenant-scoped use-case orchestration belong in `packages/application` or `packages/contracts` as appropriate. SQL tenant filters and indexes belong in `packages/infrastructure` and migrations. Route shape, request dependency resolution, and response mapping belong in `apps/api`. Organization switching and tenant-aware UX belong in `apps/web`.

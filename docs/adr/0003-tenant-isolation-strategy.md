# ADR 0003: Tenant isolation strategy

- Status: Accepted
- Date: 2026-07-20

## Context

WorkflowForge needs organization-level tenancy for identity, membership, authorization, audit, and future workflow data. The Phase 1 architecture uses PostgreSQL as the durable source of truth and application use cases behind explicit package boundaries.

Tenant isolation must be understandable, testable, and compatible with local development, API routes, workers, and future migrations.

## Decision

Tenant-scoped API routes will use organization route parameters:

```text
/api/v1/organizations/{organization_id}/...
```

The API resolves a server-side `TenantContext` from the authenticated user, active organization, active membership, and code-defined permission map:

```python
TenantContext(
    user_id,
    organization_id,
    membership_id,
    role,
    permissions,
)
```

WorkflowForge will never trust organization IDs from arbitrary request bodies.

Phase 2 tenant isolation uses API tenant validation, explicit `TenantContext` in application use cases, tenant-scoped repository interfaces, organization foreign keys, composite tenant-aware uniqueness constraints, and indexes beginning with `organization_id` where appropriate.

PostgreSQL row-level security is deferred.

## Alternatives considered

PostgreSQL row-level security from the start was considered. It can provide strong defense-in-depth, but it requires careful connection-pool and transaction-context management, especially with a single application database role, background workers, migrations, and operational scripts.

Subdomain or header-only tenant context was considered. It can be useful later, but route parameters are explicit, easy to test, and fit versioned REST routes.

Tenant IDs in request bodies were considered. They are rejected because body-provided tenant context is too easy to spoof or apply inconsistently.

Separate databases per tenant were considered. They add operational complexity before WorkflowForge has evidence that tenant scale or isolation needs justify it.

## Consequences

Tenant context is visible in route shape and explicit in use-case signatures. Repository contracts must be tenant-aware for tenant-owned data. Database schema design must include organization foreign keys and tenant-aware uniqueness.

The application must maintain discipline: every tenant-owned query must be constrained deliberately. Architecture tests and code review should reinforce that discipline.

## Security implications

Cross-tenant resources whose existence must remain hidden return `404`. Authenticated users who lack permission on a visible tenant resource receive `403`. Tenant context is resolved server-side and cannot come from arbitrary request bodies.

RLS is not used as the first enforcement layer in Phase 2. The compensating control is strict API, use-case, and repository enforcement.

## Future migration path

PostgreSQL RLS may be introduced later as defense-in-depth once tenant-owned tables, repository boundaries, transaction context handling, and operational patterns are stable.

If tenant scale or customer requirements demand stronger physical isolation, the organization key and tenant-aware repositories provide a path toward partitioning or separate databases.

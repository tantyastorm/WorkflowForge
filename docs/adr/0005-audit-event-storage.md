# ADR 0005: Audit event storage

- Status: Accepted
- Date: 2026-07-20

## Context

WorkflowForge needs a durable audit history for identity, tenancy, authorization, security-sensitive changes, and future workflow operations. Audit data must be tenant-aware, queryable, and safe to retain.

The Phase 1 architecture uses PostgreSQL for durable product state and structured logs for operational diagnostics.

## Decision

Audit records will be stored durably in PostgreSQL and treated as append-only through application behavior. WorkflowForge will expose no update or delete API for audit records.

Audit records include:

- `event_id`
- `organization_id` nullable
- `actor_user_id` nullable
- `target_type`
- `target_id` nullable
- `event_type`
- `occurred_at`
- `request_id` nullable
- `source_ip` nullable
- `user_agent` nullable
- Structured metadata.

Metadata is bounded in size and must not contain secrets, raw tokens, token digests, plaintext passwords, API keys, provider credentials, or large request and response bodies.

Audit queries are tenant-aware. Global events are allowed only when deliberately outside an organization, such as registration, login failures before tenant selection, bootstrap, or security events that cannot be attributed to one tenant.

## Alternatives considered

Application logs only were considered. Logs are useful for operations, but they are not a tenant-aware product audit store and may have different retention, access, and query behavior.

Event sourcing was considered. It is broader than the current need and would make audit persistence depend on a system-wide event model that WorkflowForge has not yet justified.

Mutable audit records were considered. They are rejected because audit history should be append-only through product behavior.

External audit storage was considered. It may be useful later, but PostgreSQL keeps the initial system simple and transactional with product state.

## Consequences

Audit writes can participate in the same transaction as security-sensitive state changes where appropriate. Tenant-aware audit reads are straightforward to model through repository interfaces.

The system must define bounded metadata rules and avoid treating audit as a dumping ground for raw payloads.

## Security implications

Audit data may contain sensitive operational context, so tenant-scoped audit reads require `audit.read`. Cross-tenant audit records are not visible through organization routes. Global audit events need deliberate policy handling.

No secret or token material is stored in audit records. Source IP and user agent are allowed but should be treated as security-sensitive metadata.

## Future migration path

If audit volume grows, records can be partitioned by time and organization or exported to external security tooling. The append-only event shape can also support retention policies and archival without changing application audit semantics.

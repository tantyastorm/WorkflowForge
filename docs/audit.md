# Audit

This document records the planned WorkflowForge audit foundation for Phase 2. It is architectural documentation, not an implementation record.

## Purpose

Audit records provide durable security and operational history for identity, tenancy, authorization, and future workflow activity. They are not a general logging table and do not replace structured application logs.

## Storage Model

Audit records are append-only through application behavior. There is no update or delete API.

Planned fields:

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

Audit metadata must be bounded in size. It must not contain secrets, raw tokens, token digests, plaintext passwords, API keys, provider credentials, or large request and response bodies.

## Tenant Awareness

Tenant-owned audit queries are tenant-aware and constrained by organization. Global events are allowed only when the event is deliberately outside an organization, such as registration, login failures before tenant selection, bootstrap events, or security events that cannot be attributed to one organization.

Global events require deliberate handling in application policy and query paths so organization-scoped users do not gain broad visibility by accident.

## Event Sources

Audit events should be written by application use cases after authorization decisions and domain invariants are evaluated. HTTP routes may pass request context such as request ID, source IP, and user agent into the use case or audit port, but route handlers should not become the owner of audit semantics.

## Query Behavior

Audit reads require `audit.read` in the active `TenantContext`. Auditors receive read-only audit and operational visibility. Cross-tenant audit records must not be visible through organization-scoped routes.

## Architecture Boundaries

Audit event semantics belong in `packages/domain` where they are durable product concepts. Audit write and query ports belong in `packages/application` or `packages/contracts` as appropriate. PostgreSQL persistence belongs in `packages/infrastructure`. HTTP request metadata collection and response mapping belong in `apps/api`. Audit viewing UX belongs in `apps/web`.

# Audit

This document records the WorkflowForge audit foundation for Phase 2.

## Purpose

Audit records provide durable security and operational history for identity, tenancy, authorization, and future workflow activity. They are not a general logging table and do not replace structured application logs.

## Storage Model

Audit records are durable PostgreSQL rows in `security_audit_events`. They are append-only through application behavior. There is no update or delete API.

Planned fields:

- `id`
- `organization_id` nullable
- `actor_user_id` nullable
- `session_id` nullable
- `event_type`
- `outcome`
- `occurred_at`
- `request_id` nullable
- `source_ip` nullable
- `user_agent` nullable
- Structured `metadata`
- `created_at`

Audit metadata is bounded in size. It must not contain secrets, raw tokens, token digests, plaintext passwords, password hashes, API keys, provider credentials, cookies, CSRF values, authorization headers, raw request headers, exception reprs, or request and response bodies.

`source_ip` stores the direct client address reported by the ASGI server. Proxy headers are not trusted in Phase 2. `user_agent` is stored only as a bounded string and is treated as security-sensitive metadata.

## Event Taxonomy

Phase 2 records the smallest useful identity and authorization taxonomy:

- `authentication.login_succeeded`
- `authentication.login_failed`
- `authentication.login_rate_limited`
- `authentication.access_token_rejected`
- `session.created`
- `session.refreshed`
- `session.refresh_failed`
- `session.refresh_rate_limited`
- `session.refresh_replay_detected`
- `session.revoked`
- `session.revoked_all`
- `bootstrap.owner_created`
- `bootstrap.refused`
- `security.rate_limit_backend_unavailable`
- `tenancy.access_denied`
- `tenancy.inactive_membership`
- `tenancy.inactive_organization`
- `authorization.permission_denied`
- `credential.password_set`
- `credential.password_replaced`

Successful tenant context resolution and successful permission checks are not recorded in Phase 2 because they would create high-volume audit noise before audit viewing and retention controls exist.

Outcomes are queryable separately from event names: `success`, `failure`, `denied`, and `replay_detected`.

## Transaction Strategy

Security-significant successful state changes record audit rows in the same transaction as the business state. Login session creation, refresh rotation, replay revocation, logout, logout-all, and password credential changes use this strategy so audit and state do not contradict each other.

Failure and denial events that have no successful business transaction use a dedicated audit transaction. Login failures, refresh failures, rate-limit denials, rejected access tokens, tenant denials, inactive tenant state, and permission denials are committed independently so they survive the failed request when audit persistence is available.

Same-transaction audit persistence failures are translated to `AuditPersistenceError` and roll back the owning business transaction. Independent failure-event audit persistence failures are best-effort: they are logged structurally with request correlation context and do not replace the original public `401` or `403` response. Phase 2 does not silently discard durable audit failures, and it does not add Kafka, Redis streams, or an outbox subsystem.

## Tenant Awareness

Tenant-owned audit queries are tenant-aware and constrained by organization. Global events are allowed only when the event is deliberately outside an organization, such as registration, login failures before tenant selection, bootstrap events, or security events that cannot be attributed to one organization.

Global events require deliberate handling in application policy and query paths so organization-scoped users do not gain broad visibility by accident.

## Event Sources

Audit events should be written by application use cases after authorization decisions and domain invariants are evaluated. HTTP routes may pass request context such as request ID, source IP, and user agent into the use case or audit port, but route handlers should not become the owner of audit semantics.

## Query Behavior

Audit reads require `audit.read` in the active `TenantContext`. Auditors receive read-only audit and operational visibility. Cross-tenant audit records must not be visible through organization-scoped routes.

The application query port supports bounded newest-first reads for recent events, actor user, organization, and event type. Public audit API endpoints are deferred.

## Architecture Boundaries

Audit event semantics belong in `packages/domain` where they are durable product concepts. Audit write and query ports belong in `packages/application` or `packages/contracts` as appropriate. PostgreSQL persistence belongs in `packages/infrastructure`. HTTP request metadata collection and response mapping belong in `apps/api`. Audit viewing UX belongs in `apps/web`.

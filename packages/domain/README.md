# Domain Package

Belongs here: core WorkflowForge business concepts, invariants, policies, and pure domain behavior.

Does not belong here: framework code, database access, queues, HTTP clients, browser automation clients, AI provider SDKs, or process startup code.

Owner: inner domain layer.

Dependency direction: must remain independent of application frameworks and infrastructure. It may use stable contracts only when those contracts are domain-neutral.

Python workspace distribution: `workflowforge-domain`.

## Documents

The document domain foundation defines metadata for future uploaded documents without depending on FastAPI, SQLAlchemy, S3, Celery, or AI providers.

Current concepts:

- `DocumentId`: strongly typed UUID identifier.
- `ContentHash`: validated lowercase SHA-256 hex digest.
- `StorageObjectKey`: deterministic, path-safe metadata key derived from the content hash.
- `DocumentStatus`: `registered`, `stored`, and `failed`.
- `Document`: immutable metadata aggregate with original filename, media type, byte size, content hash, object key, lifecycle status, and timestamps.

The current storage key format is `documents/sha256/<first-two-hex>/<next-two-hex>/<sha256>`. The original filename is kept only as a normalized user-facing display value and is not used as the object key.

## Identity And Tenancy

The identity and tenancy domain foundation defines framework-independent users, organizations, memberships, roles, membership statuses, identity value objects, lifecycle errors, and pure membership policies.

Current concepts:

- `EmailAddress`: preserves display email and compares by `email.strip().casefold()` identity.
- `OrganizationSlug`: explicit lowercase public organization slug.
- `Role`: `owner`, `admin`, `operator`, `reviewer`, and `auditor`.
- `MembershipStatus`: `invited`, `active`, `suspended`, and `removed`.
- `Permission`: stable named organization permissions for current identity and security behavior.
- `permissions_for_role`: immutable code-defined role-to-permission resolution.
- `User`: identity entity with email, display name, active state, and lifecycle timestamps.
- `Organization`: tenant entity with name, immutable slug, active state, and lifecycle timestamps.
- `Membership`: user-to-organization relationship with explicit invite, activation, suspension, reactivation, removal, and role-change transitions.
- `MembershipPolicy`: pure policy checks including the last-active-owner invariant.

This package does not define permission resolution, tenant context, repositories, authentication sessions, password credentials, API schemas, SQLAlchemy mappings, or audit persistence.

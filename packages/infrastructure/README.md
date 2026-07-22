# Infrastructure Package

Belongs here: implementations for persistence, queues, storage, browser automation, AI provider clients, and external system adapters.

Does not belong here: domain rules, application use case definitions, frontend code, or process entry points.

Owner: infrastructure adapter layer.

Dependency direction: implements ports defined by inner layers and may depend on `packages/domain` and `packages/contracts`. Apps compose these adapters with application services.

Python workspace distribution: `workflowforge-infrastructure`.

## Database Foundation

WorkflowForge supports PostgreSQL only. Runtime database access uses SQLAlchemy async engines with `asyncpg`; Alembic migrations use synchronous SQLAlchemy with Psycopg 3.

Infrastructure owns engine, session, metadata, and health-check mechanics. Domain and application packages must remain independent of SQLAlchemy.

Application use cases own transaction boundaries. Session helpers do not commit implicitly; they roll back on exceptions and always close the session.

Migrations are explicit operational commands. API startup must not run migrations automatically, and multiple API processes must not race to migrate.

## Dependency Health Adapters

Infrastructure provides concrete dependency health adapters for:

- PostgreSQL with an async SQLAlchemy `SELECT 1` check.
- Redis with an async `PING` check.
- S3-compatible object storage with a bucket `head_bucket` check.
- Celery worker availability with a bounded inspect ping.
- Scheduler visibility with a Redis heartbeat timestamp.

Adapters return transport-neutral health contracts, measure non-negative latency, use bounded timeouts, and sanitize failures. They do not expose credentials, raw connection URLs, driver exception messages, or stack traces.

Redis and S3 clients are created through explicit factories. No database, Redis, S3, or Celery broker client is created at module import time. Redis remains transient coordination infrastructure, not durable workflow state. S3 health checks verify bucket reachability and do not write objects.

## Celery Task Infrastructure

`workflowforge_infrastructure.tasks` owns the Celery app factory, explicit diagnostic task registration, periodic schedule registration, and worker/scheduler health checks.

The Celery app is named `workflowforge`, uses Redis as broker and result backend, accepts JSON only, serializes tasks and results as JSON, enables UTC with timezone `UTC`, disables late acknowledgements for the current diagnostic tasks, uses a prefetch multiplier of `1`, tracks task start state, applies bounded hard and soft task time limits, and registers explicit default and diagnostic queues.

Celery broker and result backend URLs are derived from the typed Redis settings by default, using separate Redis databases for broker and diagnostic result metadata. Explicit URL overrides are supported and stored as secrets so credentials are not exposed through reprs.

Registered Phase 1 tasks:

- `system.diagnostics.echo`
- `system.diagnostics.scheduler_heartbeat`

No business tasks are registered in this foundation.

## Document Persistence

Infrastructure implements the application document repository port with SQLAlchemy. The `documents` table stores metadata only:

- document ID;
- normalized original filename;
- media type;
- byte size;
- SHA-256 content hash;
- deterministic storage object key;
- lifecycle status;
- creation and update timestamps.

The table enforces non-negative byte size, valid initial lifecycle statuses, unique content hashes, and unique storage object keys. The repository maps rows to domain objects and translates duplicate inserts into sanitized application errors. It does not expose ORM models outside infrastructure and does not write file bytes to MinIO.

## Identity Persistence

Infrastructure implements application repository ports for users, organizations, and memberships with SQLAlchemy. The `users` table stores display email, normalized email, display name, active state, and lifecycle timestamps. The `organizations` table stores organization name, slug, active state, and lifecycle timestamps. The `memberships` table stores user-to-organization membership role, status, and lifecycle timestamps.

Role and membership status values are persisted as bounded strings with database check constraints rather than PostgreSQL native enums. This keeps public enum values stable while avoiding enum-alter migration friction.

Membership repository methods require organization identity for tenant-owned membership lookups where appropriate. Repositories map rows to validated domain entities, translate duplicate email, slug, and membership conflicts into application errors, and do not commit transactions implicitly.

Password credentials are persisted in `password_credentials`, keyed one-to-one
by `user_id` with a cascading foreign key to `users`. The SQLAlchemy password
credential repository is the only normal persistence path for password hashes;
ordinary user repository methods do not return credential state.

## Password Hashing

Infrastructure provides an Argon2id `PasswordHasher` adapter using
`argon2-cffi`. Hashes use the library format that embeds salt, algorithm, and
parameters. Verification handles mismatched, malformed, and unsupported hashes
safely by returning `False`, and the adapter exposes a dummy hash for
missing-account authentication paths.

Infrastructure also provides a SHA-256 refresh-token digest adapter for
server-generated high-entropy opaque refresh tokens. This adapter is deliberately
separate from password hashing and supports deterministic lookup plus
constant-time digest verification.

Infrastructure provides an HS256 JWT access-token codec using PyJWT. It validates
the configured issuer and audience, requires `sub`, `sid`, `jti`, `iat`, `exp`,
`iss`, and `aud`, restricts algorithms to HS256, and maps JWT library failures to
sanitized application errors. It also provides secure refresh-token generation
using Python `secrets`, a UTC clock adapter, and a UUID4 generator adapter.

## Session Persistence

Infrastructure implements the application session repository with PostgreSQL
tables for `auth_sessions` and `refresh_tokens`. A user may have multiple
sessions. Sessions store user ID, creation/update/expiry timestamps, and
revocation timestamp. Refresh-token rows store digests only, session ID, token
family ID, generation, issued/expiry/use/revocation timestamps, and replacement
lineage.

Refresh rotation inserts the replacement token and consumes the expected current
token in one transaction using constrained SQL update semantics. The update
requires the expected session ID, digest, generation, unused/unrevoked token
state, and active session state. Stale rotation attempts raise a sanitized
application conflict. Revoke-one and revoke-all mark sessions and current
refresh credentials revoked without committing implicitly.

## Audit Persistence

Infrastructure implements audit ports with `security_audit_events` in
PostgreSQL. The table stores typed event names, outcomes, actor/user,
organization, session, correlation/request metadata, bounded source IP and user
agent, structured JSONB metadata, and timestamps.

Audit foreign keys use `ON DELETE SET NULL` so hard-deleting users,
organizations, or sessions does not cascade away audit evidence. The repository
exposes append and bounded newest-first query operations only; it does not expose
update or delete methods and does not commit transactions implicitly.

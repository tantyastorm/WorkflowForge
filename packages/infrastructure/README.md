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

# Migrations

Belongs here: future database migration files and migration documentation.

Does not belong here: ORM models, runtime database configuration, application services, or generated local database files.

Owner: persistence and release operations.

Dependency direction: migrations are applied by deployment and operations tooling. No migration framework is introduced in this commit.

## Alembic Foundation

Migrations use Alembic against PostgreSQL. Runtime application access uses async SQLAlchemy with `asyncpg`; migration execution uses synchronous SQLAlchemy with Psycopg 3.

The database URL in `alembic.ini` is a placeholder. `migrations/env.py` reads validated `WORKFLOWFORGE_DATABASE_*` settings and supplies the synchronous migration URL.

Run migrations explicitly from the repository root:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base
```

API startup must not run migrations automatically. Docker Compose includes a dedicated migration service that runs `alembic upgrade head`.

Production favors forward migrations. Downgrades are supported where practical for development and validation.

## Local Compose Migration Service

Docker Compose includes a one-shot `migrate` service that runs:

```powershell
uv run alembic upgrade head
```

The API depends on successful completion of this service. Migrations are not run from API startup or lifespan handling.

When running migrations from the host against Compose PostgreSQL, use `localhost` and the mapped PostgreSQL host port. Inside Compose, the database hostname is `postgres`.

Useful host-side validation commands:

```powershell
$env:WORKFLOWFORGE_DATABASE_HOST = "localhost"
$env:WORKFLOWFORGE_DATABASE_PORT = "5432"
uv run pytest -m integration
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base
uv run alembic upgrade head
```

The Phase 1 baseline migration intentionally created no business tables. Phase 2 adds `0002_create_documents`, which created the first document metadata table, then `0003` through `0007` added identity, memberships, password credentials, sessions, refresh tokens, and security audit events.

Phase 3 Step 2 adds `0008_doc_tenancy_versions`, which evolves documents into tenant-owned aggregate metadata and creates `document_versions` plus `document_artifacts`.

`0008` backfills legacy `documents` rows by creating version `1` for each row, preserving the legacy object key exactly as stored. Legacy document ownership is assigned only when the database has exactly one organization and either exactly one active owner for that organization or exactly one user. If ownership is ambiguous, the migration fails with an actionable error instead of silently assigning rows to an arbitrary organization.

The new duplicate policy is tenant-scoped: `document_versions` enforces unique `(organization_id, content_hash)` and `(organization_id, storage_object_key)`. The same SHA-256 bytes in one tenant map to the existing document resource; the same bytes in another tenant are allowed. Downgrading populated Step 2 data into the old Phase 2 global-unique document table may fail if multiple tenants contain the same hash or storage key.

Alembic does not move object-storage data. Legacy object keys are preserved in `document_versions.storage_object_key`; any physical object-key migration must be deliberate operational work outside the database migration.

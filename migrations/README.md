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

API startup must not run migrations automatically. A later local infrastructure commit may add a dedicated migration service that runs `alembic upgrade head`.

Production favors forward migrations. Downgrades are supported where practical for development and validation.

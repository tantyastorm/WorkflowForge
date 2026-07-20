# Infrastructure

Belongs here: deployment, operations, observability, and environment provisioning assets.

Does not belong here: application business logic, package source code, secrets, or local generated volumes.

Owner: operations and platform maintainers.

Dependency direction: infrastructure assets deploy or configure apps and services; application layers must not import from this directory.

## Local Docker Compose

Create a local environment file from the tracked template:

```powershell
Copy-Item .env.example .env
```

Start the local foundation:

```powershell
docker compose up --build
```

Background startup is also supported:

```powershell
docker compose up --build -d
```

Current services:

- `postgres`: PostgreSQL on host port `5432` by default.
- `redis`: Redis with append-only persistence on host port `6379` by default.
- `minio`: S3-compatible object storage on host port `9000`, console on `9001`.
- `minio-init`: one-shot bucket initialization for `WORKFLOWFORGE_S3_BUCKET`.
- `migrate`: one-shot `uv run alembic upgrade head`.
- `api`: FastAPI on host port `8000`.

Compose service hostnames are `postgres`, `redis`, and `minio`. Host-side tools use `localhost` plus the mapped host port.

Named volumes preserve development data across ordinary stops:

- `postgres_data`
- `redis_data`
- `minio_data`

Normal shutdown:

```powershell
docker compose down
```

Destructive reset:

```powershell
docker compose down -v
```

The `-v` reset deletes local development database, Redis, and MinIO data.

The API waits for PostgreSQL, Redis, and MinIO health checks, successful MinIO bucket initialization, and successful migrations. API startup does not run Alembic itself.

This foundation intentionally excludes workers, scheduler, frontend, Celery, application Redis/S3 adapters, and `/health/dependencies`.

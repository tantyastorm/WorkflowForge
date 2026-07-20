# API App

Belongs here: the backend API process entry point, HTTP routing composition, request adapters, and API-specific wiring.

Does not belong here: domain rules, infrastructure implementations, worker jobs, scheduler logic, or frontend code.

Owner: `apps/api` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring.

Python workspace distribution: `workflowforge-api`.

## Application Foundation

The API is built through `workflowforge_api.factory.create_app(settings=None)`. Tests can pass explicit validated settings; process startup uses `workflowforge_api.main:app` for Uvicorn.

Run from the repository root:

```powershell
uv run uvicorn workflowforge_api.main:app --host 127.0.0.1 --port 8000
```

The Docker Compose API service uses the same application entry point:

```powershell
docker compose up --build api
```

The container runs Uvicorn without reload, exposes port `8000` by default, waits for PostgreSQL health, Redis health, MinIO health, successful MinIO bucket initialization, and the dedicated Alembic migration service. API startup does not run migrations.

Operational health routes are process-level routes outside product API versioning:

- `GET /health/live` returns `200` when the process can answer HTTP.
- `GET /health/ready` returns `200` after FastAPI startup completes and `503` before startup or after shutdown.

These routes do not check PostgreSQL, Redis, object storage, workers, or the scheduler. A future `/health/dependencies` route will report real dependency health once local infrastructure exists; this app does not return placeholder dependency states.

Product routes will be versioned under `WORKFLOWFORGE_API_V1_PREFIX`, which defaults to `/api/v1`. No business routes are exposed yet.

API documentation is available at `/docs`, `/redoc`, and `/openapi.json` when `WORKFLOWFORGE_API_DOCS_ENABLED=true`. Those routes are disabled when the setting is false.

Every response includes `X-Correlation-ID`. Incoming safe correlation IDs are preserved; missing or malformed values are replaced and bound to request-local structured logging context.

Smoke-test a running local Compose API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-WebRequest http://127.0.0.1:8000/openapi.json
```

The dependency-health endpoint is still absent in this step.

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
- `GET /health/dependencies` returns real dependency health for PostgreSQL, Redis, object storage, the Celery worker, and the scheduler heartbeat.

Liveness and readiness do not check external dependencies. Dependency health runs bounded checks concurrently in this deterministic order: `postgresql`, `redis`, `object_storage`, `worker`, `scheduler`. It returns HTTP `200` when all required dependencies are healthy and HTTP `503` when any required dependency is unhealthy. Diagnostics are sanitized and do not include credentials, raw driver exceptions, broker URLs, or stack traces.

API startup does not wait for a Celery worker or scheduler heartbeat. Those states are operational dependencies reported through `/health/dependencies`, while `/health/ready` remains scoped to FastAPI process readiness.

Product routes are versioned under `WORKFLOWFORGE_API_V1_PREFIX`, which defaults to `/api/v1`.

Implemented authentication routes:

- `POST /api/v1/auth/login` accepts email/password JSON, returns a short-lived bearer access token, and sets refresh and CSRF cookies.
- `POST /api/v1/auth/refresh` reads the refresh token from the HttpOnly cookie, requires double-submit CSRF proof, rotates the durable refresh token, and returns a new access token.
- `POST /api/v1/auth/logout` requires a bearer access token and CSRF proof, revokes the current session, and clears auth cookies.
- `POST /api/v1/auth/logout-all` requires a bearer access token and CSRF proof, revokes every active session for the current user, and clears local auth cookies.
- `GET /api/v1/auth/me` requires a bearer access token and returns minimal authenticated principal metadata.
- `GET /api/v1/auth/organizations` requires a bearer access token and returns the active organizations available to the current authenticated user.

Refresh tokens are never returned in JSON. HTTP cookie handling, CSRF validation, bearer parsing, and error mapping live in this API package; identity lifecycle rules remain in `packages/application`.

Tenant authorization proof routes live under
`/api/v1/organizations/{organization_id}/tenancy`:

- `GET /context` requires bearer authentication, resolves active membership for
  the selected organization, and returns safe tenant context metadata.
- `GET /authorized-probe` additionally requires the `security.manage`
  permission and exists only to prove reusable permission dependency
  composition.

Tenant selection comes from the organization route parameter, not from the
access token or request body. Public tenant-resolution failures return a generic
`403` to avoid unnecessary organization and membership enumeration.

API documentation is available at `/docs`, `/redoc`, and `/openapi.json` when `WORKFLOWFORGE_API_DOCS_ENABLED=true`. Those routes are disabled when the setting is false.

Every response includes `X-Correlation-ID`. Incoming safe correlation IDs are preserved; missing or malformed values are replaced and bound to request-local structured logging context.

Security audit request metadata reuses that correlation ID as `request_id`.
Audit context stores only the direct ASGI client IP when it parses as an IP
address and a bounded `User-Agent` string. Proxy forwarding headers, cookies,
authorization headers, request bodies, and full header sets are not stored in
audit events.

Smoke-test a running local Compose API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-WebRequest http://127.0.0.1:8000/health/dependencies
Invoke-WebRequest http://127.0.0.1:8000/openapi.json
```

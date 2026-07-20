# WorkflowForge

WorkflowForge is an open-source operations platform for building, evaluating, and running reliable AI-assisted workflows across documents, APIs, browser automation, human approvals, and external systems.

## Project Status

WorkflowForge has completed the Phase 1 alpha foundation and is now in early Phase 2 product foundation work. The repository layout, contribution standards, architecture boundaries, Python workspace, database migration foundation, local infrastructure, API health foundation, Celery worker/scheduler process foundations, React frontend foundation, frontend system-status view, CI validation, and document metadata persistence foundation are in place. Identity, tenancy, authorization, security, and audit foundations are documented as planned Phase 2 architecture decisions.

This stage does not implement file upload endpoints, authentication runtime behavior, tenant runtime behavior, workflow execution features, document extraction or classification, business worker tasks, scheduler workflow triggers, final dashboard UI, or object-storage writes.

## Planned Capabilities

- Workflow authoring and execution across documents, APIs, browser tasks, and external systems.
- Human approval checkpoints for sensitive operations.
- Evaluation support for reliability, repeatability, and regression detection.
- Operational visibility into workflow runs, task outcomes, and integration behavior.
- Modular integration points for AI providers, queues, storage, browser automation, and third-party systems.

## Architecture Direction

WorkflowForge V1 is planned as a modular monolith with independently runnable processes:

- `apps/api` exposes the backend API process.
- `apps/worker` runs background workflow and task execution.
- `apps/scheduler` coordinates scheduled work.
- `apps/web` contains the React frontend.

Core behavior is organized by dependency direction:

```text
apps/api
apps/worker
apps/scheduler
        |
        v
packages/application
        |
        +-- packages/domain
        +-- packages/contracts

packages/infrastructure
        +-- packages/application
        +-- packages/domain
        +-- packages/contracts
```

The domain layer remains independent of frameworks and infrastructure. Application orchestration depends on domain and contracts, but not directly on infrastructure. Infrastructure implements ports and adapters defined by the application and contract layers. Apps are composition roots that wire processes together.

## Repository Map

```text
.github/               Issue and pull request templates.
apps/                  Runnable process entry points.
packages/              Domain, application, infrastructure, and contract layers.
integrations/          Integration-specific adapters and notes.
examples/              Small examples for future users and contributors.
demo_data/             Non-secret sample data for demos and tests.
tests/                 Architecture, integration, and system test areas.
migrations/            Future database migration workspace.
docs/                  Architecture records and repository documentation.
infrastructure/        Deployment and operations assets.
scripts/               Developer and automation scripts.
```

## Current Scope

Phase 2 has started with document metadata and identity/tenancy architecture planning. The implemented slice is document metadata only: a framework-independent document domain model, application services for registration and retrieval, a SQLAlchemy repository adapter, and an Alembic `documents` table. File upload, object writes, authentication runtime behavior, tenant runtime behavior, authorization enforcement, audit persistence, extraction, classification, workflow execution, and document UI remain deferred.

## Documentation

- [Product definition](docs/product.md)
- [V1 scope](docs/v1-scope.md)
- [Architecture](docs/architecture.md)
- [Identity](docs/identity.md)
- [Tenancy](docs/tenancy.md)
- [Authorization](docs/authorization.md)
- [Security](docs/security.md)
- [Audit](docs/audit.md)
- [Phase 1 alpha readiness](docs/phase-1-readiness.md)
- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [ADR 0002: Authentication and session model](docs/adr/0002-authentication-and-session-model.md)
- [ADR 0003: Tenant isolation strategy](docs/adr/0003-tenant-isolation-strategy.md)
- [ADR 0004: Role and permission model](docs/adr/0004-role-and-permission-model.md)
- [ADR 0005: Audit event storage](docs/adr/0005-audit-event-storage.md)
- [Glossary](docs/glossary.md)

## Backend Workspace

The Python backend uses Python 3.12, `uv`, and editable workspace packages. After activating `.venv`, install the backend workspace with:

```powershell
uv sync --all-packages --group dev
```

Current quality checks:

```powershell
uv sync --all-packages --group dev
uv run python scripts/validate_architecture.py
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages migrations scripts tests
uv run pytest -m "not integration"
uv run pytest -m integration
uv run pytest --cov --cov-report=term-missing
```

Database migration commands:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base
```

Database integration tests require a real PostgreSQL database configured through `WORKFLOWFORGE_DATABASE_*` environment variables.

GitHub Actions runs separate backend, frontend, and Docker validation workflows on pull requests, pushes to `main`, and manual dispatch. The backend workflow validates architecture, Ruff formatting and linting, MyPy, unit tests, integration tests, and the existing coverage threshold of 80%. The integration job starts the real Docker Compose stack, waits for API dependency health, runs all integration tests without skips, prints container logs on failure, and tears down CI volumes afterward. The Docker workflow validates Compose syntax and builds the shared backend image used by the API, migration, worker, and scheduler services. The frontend workflow runs the locked pnpm install, Prettier, ESLint, TypeScript, Vitest, and the production build.

Local infrastructure starts with Docker Compose:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis, MinIO, a one-shot MinIO bucket initializer, a one-shot Alembic migration service, the API, the Celery worker, the Celery Beat scheduler, and the Vite frontend.

Run the API process from the repository root:

```powershell
uv run uvicorn workflowforge_api.main:app --host 127.0.0.1 --port 8000
```

Run the worker process from the repository root:

```powershell
uv run celery -A workflowforge_worker.main:app worker --loglevel=INFO
```

Run the scheduler process from the repository root:

```powershell
uv run celery -A workflowforge_scheduler.main:app beat --loglevel=INFO
```

Run the safe diagnostic task against a running worker:

```powershell
uv run python scripts/run_diagnostic_task.py --message hello --timeout 10
```

Open the system-status frontend:

```text
http://127.0.0.1:5173/status
```

API health endpoints:

- `GET /health/live` confirms the API process is alive and does not check external dependencies.
- `GET /health/ready` confirms FastAPI startup completed for the current process instance.
- `GET /health/dependencies` checks PostgreSQL, Redis, object storage, worker availability, and scheduler heartbeat visibility concurrently.

Dependency health returns `200` only when all required dependencies are healthy and `503` when one or more are unhealthy. The order is `postgresql`, `redis`, `object_storage`, `worker`, `scheduler`. Responses include sanitized details and bounded latency measurements. API readiness remains independent from worker and scheduler availability. API documentation is available at `/docs`, `/redoc`, and `/openapi.json` unless disabled with `WORKFLOWFORGE_API_DOCS_ENABLED=false`. Responses include `X-Correlation-ID` for request tracing.

Default local ports are PostgreSQL `5432`, Redis `6379`, MinIO API `9000`, MinIO console `19001`, API `8000`, and frontend `5173`. Compose services use internal hostnames such as `postgres`, `redis`, and `minio`; host-side tools should use `localhost` with the configured host ports.

Stop local services with:

```powershell
docker compose down
```

Use `docker compose down -v` only for a destructive reset; it deletes local PostgreSQL, Redis, and MinIO development data.

Workspace distributions are `workflowforge-domain`, `workflowforge-contracts`, `workflowforge-application`, `workflowforge-infrastructure`, `workflowforge-api`, `workflowforge-worker`, and `workflowforge-scheduler`.

## Frontend Workspace

The frontend uses React, TypeScript, Vite, React Router, TanStack Query, Zod, Vitest, Testing Library, ESLint, Prettier, and pnpm. Use Node.js 24 LTS or another current Node LTS compatible with Vite.

Install and run from the repository root:

```powershell
corepack pnpm --dir apps/web install
corepack pnpm --dir apps/web dev --host 127.0.0.1
```

The frontend environment file is `apps/web/.env.example`; copy it to an untracked local `.env` when needed. The required public setting is:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Frontend quality checks:

```powershell
corepack pnpm --dir apps/web install --frozen-lockfile
corepack pnpm --dir apps/web format:check
corepack pnpm --dir apps/web lint
corepack pnpm --dir apps/web typecheck
corepack pnpm --dir apps/web test:run
corepack pnpm --dir apps/web build
```

The `/status` route shows live platform health from `GET /health/live`, `GET /health/ready`, and `GET /health/dependencies`. It displays API liveness, API readiness, PostgreSQL, Redis, object storage, worker, and scheduler status. The page refreshes automatically every 20 seconds through TanStack Query and also supports manual refresh.

Run the backend and frontend together:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Open `http://127.0.0.1:5173/status` to inspect real local health. The frontend remains a Phase 1 operational view, not final product branding or a business dashboard.

## Contributing

WorkflowForge is not yet ready for broad external contribution. Early contributions should be small, focused, and aligned with the architecture boundaries in this repository. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/commits.md](docs/commits.md).

## License

WorkflowForge is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

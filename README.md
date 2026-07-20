# WorkflowForge

WorkflowForge is an open-source operations platform for building, evaluating, and running reliable AI-assisted workflows across documents, APIs, browser automation, human approvals, and external systems.

## Project Status

WorkflowForge is in early Phase 1 foundation work. The repository layout, contribution standards, architecture boundaries, Python workspace, database migration foundation, local infrastructure, and API health foundation are in place.

This stage does not implement frontend tooling, authentication, workflow execution features, background workers, scheduler behavior, Celery tasks, or business object-storage APIs.

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
        +-- packages/domain
        +-- packages/contracts
```

The domain layer remains independent of frameworks and infrastructure. Application orchestration depends on domain and contracts, but not directly on infrastructure. Infrastructure implements ports and adapters defined by the inner layers. Apps are composition roots that wire processes together.

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

## Phase 1 Scope

Current Phase 1 work is limited to focused foundations. The API process currently exposes health endpoints only; product routes, authentication, background execution, and frontend runtime will be introduced in later commits.

## Documentation

- [Product definition](docs/product.md)
- [V1 scope](docs/v1-scope.md)
- [Architecture](docs/architecture.md)
- [ADR 0001: Modular monolith](docs/adr/0001-modular-monolith.md)
- [Glossary](docs/glossary.md)

## Backend Workspace

The Python backend uses Python 3.12, `uv`, and editable workspace packages. After activating `.venv`, install the backend workspace with:

```powershell
uv sync --all-packages --group dev
```

Current quality checks:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages scripts tests
uv run python scripts/validate_architecture.py
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

Database migration commands:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade base
```

Database integration tests require a real PostgreSQL database configured through `WORKFLOWFORGE_DATABASE_*` environment variables.

Local infrastructure starts with Docker Compose:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis, MinIO, a one-shot MinIO bucket initializer, a one-shot Alembic migration service, and the API. It does not start workers, a scheduler, a frontend, or Celery.

Run the API process from the repository root:

```powershell
uv run uvicorn workflowforge_api.main:app --host 127.0.0.1 --port 8000
```

API health endpoints:

- `GET /health/live` confirms the API process is alive and does not check external dependencies.
- `GET /health/ready` confirms FastAPI startup completed for the current process instance.
- `GET /health/dependencies` checks PostgreSQL, Redis, and object storage concurrently.

Dependency health returns `200` only when all required dependencies are healthy and `503` when one or more are unhealthy. Responses include sanitized details and bounded latency measurements. Worker health is intentionally omitted until the worker process exists. API documentation is available at `/docs`, `/redoc`, and `/openapi.json` unless disabled with `WORKFLOWFORGE_API_DOCS_ENABLED=false`. Responses include `X-Correlation-ID` for request tracing.

Default local ports are PostgreSQL `5432`, Redis `6379`, MinIO API `9000`, MinIO console `9001`, and API `8000`. Compose services use internal hostnames such as `postgres`, `redis`, and `minio`; host-side tools should use `localhost` with the configured host ports.

Stop local services with:

```powershell
docker compose down
```

Use `docker compose down -v` only for a destructive reset; it deletes local PostgreSQL, Redis, and MinIO development data.

Workspace distributions are `workflowforge-domain`, `workflowforge-contracts`, `workflowforge-application`, `workflowforge-infrastructure`, `workflowforge-api`, `workflowforge-worker`, and `workflowforge-scheduler`.

## Contributing

WorkflowForge is not yet ready for broad external contribution. Early contributions should be small, focused, and aligned with the architecture boundaries in this repository. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/commits.md](docs/commits.md).

## License

WorkflowForge is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

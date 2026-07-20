# Phase 1 Alpha Readiness

WorkflowForge `v0.1.0-alpha.1` is a release candidate for the Phase 1 foundation. Phase 1 proves the repository structure, local runtime foundation, health visibility, validation tooling, and CI discipline needed before product workflow features are added.

This release is intentionally an alpha foundation. It is not production ready for business workflow processing and does not include document intake, workflow execution, authentication, AI providers, or operator business screens.

## Completed Capabilities

- Product direction, V1 scope, glossary, architecture documentation, ADR 0001, contribution standards, issue templates, pull request template, code of conduct, license, and conventional commit guidance.
- Python 3.12 workspace managed by `uv`, with FastAPI API, Celery worker, Celery Beat scheduler, and domain, application, contracts, and infrastructure packages.
- React/Vite frontend workspace with TypeScript, React Router, TanStack Query, Zod validation, ESLint, Prettier, Vitest, and a system-status page backed by real API health endpoints.
- Docker Compose local stack for PostgreSQL, Redis, MinIO, MinIO bucket initialization, Alembic migration execution, API, worker, scheduler, and frontend.
- Operational health endpoints for API liveness, API readiness, dependency health, worker availability, scheduler heartbeat visibility, PostgreSQL, Redis, and S3-compatible storage.
- Architecture validation, Ruff formatting and linting, MyPy, backend unit and integration tests, coverage enforcement, frontend validation, Docker validation, and Dependabot.

## Service Inventory

| Service | Purpose | Default host URL or port | Evidence |
| --- | --- | --- | --- |
| `postgres` | Durable database foundation | `localhost:5432` | Compose health check plus database integration tests |
| `redis` | Queue transport and transient coordination | `localhost:6379` | Compose health check plus Redis and Celery integration tests |
| `minio` | Local S3-compatible object storage | API `http://localhost:9000`, console `http://localhost:19001` | Bucket initializer plus object-storage health tests |
| `minio-init` | Creates the local object-storage bucket | one-shot service | Compose dependency ordering |
| `migrate` | Runs Alembic migrations to head | one-shot service | Migration integration tests |
| `api` | FastAPI operational API | `http://localhost:8000` | `/health/*` and `/openapi.json` |
| `worker` | Celery worker for diagnostic task execution | internal process | Diagnostic task integration tests and dependency health |
| `scheduler` | Celery Beat heartbeat publisher | internal process | Scheduler heartbeat integration tests and dependency health |
| `web` | Vite frontend system-status view | `http://localhost:5173/status` | Frontend tests, build, and Compose service |

## Validation Matrix

| Area | Local command or check | CI coverage |
| --- | --- | --- |
| Architecture boundaries | `uv run python scripts/validate_architecture.py` | Backend Quality |
| Backend formatting | `uv run ruff format --check .` | Backend Quality |
| Backend linting | `uv run ruff check .` | Backend Quality |
| Backend typing | `uv run mypy apps packages migrations scripts tests` | Backend Quality |
| Backend unit tests | `uv run pytest -m "not integration"` | Backend Quality |
| Compose-backed integration tests | `uv run pytest -m integration` | Backend Integration |
| Coverage threshold | `uv run pytest --cov --cov-report=term-missing` with `fail_under = 80` | Backend Integration |
| Frontend formatting | `corepack pnpm --dir apps/web format:check` | Frontend Quality |
| Frontend linting | `corepack pnpm --dir apps/web lint` | Frontend Quality |
| Frontend typing | `corepack pnpm --dir apps/web typecheck` | Frontend Quality |
| Frontend tests | `corepack pnpm --dir apps/web test:run` | Frontend Quality |
| Frontend production build | `corepack pnpm --dir apps/web build` | Frontend Quality |
| Compose syntax | `docker compose config` | Docker Validation |
| Shared backend image | `docker compose build api` | Docker Validation |

## Requirement Audit

| Requirement | Evidence | Status | Changes made | Intentional deferrals |
| --- | --- | --- | --- | --- |
| Product documentation | `docs/product.md`, `docs/v1-scope.md`, glossary | Complete | Readiness summary added | Detailed feature specs remain Phase 2+ |
| Architecture documentation | `docs/architecture.md`, ADR 0001 | Complete | Removed stale Phase 1 wording | Detailed module designs follow features |
| ADRs | `docs/adr/0001-modular-monolith.md` | Complete | None | Future ADRs as decisions arise |
| Python workspace | `pyproject.toml`, package workspaces, `uv.lock` | Complete | None | Product packages remain empty until features |
| FastAPI application | `apps/api`, health routes, OpenAPI | Complete for Phase 1 | None | Product API routes deferred |
| React frontend | `apps/web`, `/status` route | Complete for Phase 1 | Compose onboarding aligned | Business UI deferred |
| PostgreSQL | Compose service, settings, health check, migration tests | Complete | None | Business tables deferred |
| Redis | Compose service, settings, health check, Celery use | Complete | None | Caches and locks deferred |
| MinIO | Compose service, bucket init, S3 health adapter | Complete | None | Business object APIs deferred |
| Celery worker | Worker app, diagnostic task, health visibility | Complete for diagnostics | None | Business tasks deferred |
| Celery scheduler | Scheduler app and heartbeat task | Complete for diagnostics | None | Workflow scheduling deferred |
| Alembic migrations | Baseline revision and integration tests | Complete for empty database | None | Business schema deferred |
| Health endpoints | `/health/live`, `/health/ready`, `/health/dependencies` | Complete for Phase 1 | None | Metrics deferred |
| Structured logging | Logging configuration and tests | Complete foundation | None | Full observability stack deferred |
| Settings and env vars | Pydantic settings, `.env.example`, tests | Complete | Added frontend Compose env documentation | Secret management deferred |
| Docker Compose startup | Compose stack with API, worker, scheduler, frontend, data services | Complete | Added `web` service and tests | Production deployment deferred |
| Backend quality tooling | Ruff, MyPy, pytest, coverage, architecture validator | Complete | None | None |
| Frontend quality tooling | Prettier, ESLint, TypeScript, Vitest, Vite build | Complete | None | None |
| GitHub Actions | Backend, frontend, Docker workflows | Complete | Docker path filters include web | Deployment workflows deferred |
| Dependabot | Weekly GitHub Actions, Python, frontend, Docker groups | Complete | None | Auto-merge deferred |
| Contribution documentation | `CONTRIBUTING.md`, templates, commit guide | Complete | None | Broader governance deferred |
| Repository standards | License, code of conduct, templates, ignores | Complete | None | None |
| Clean architecture boundaries | Validation script and architecture tests | Complete | None | Feature modules deferred |

## Health And Diagnostic Evidence

The clean-start path is:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

After startup, the API exposes:

- `GET /health/live`
- `GET /health/ready`
- `GET /health/dependencies`
- `GET /openapi.json`

The dependency health endpoint verifies PostgreSQL, Redis, object storage, worker availability, and scheduler heartbeat visibility. The worker diagnostic path is exercised through `scripts/run_diagnostic_task.py` and the integration tests. The scheduler heartbeat is exercised through integration tests and Redis-backed dependency health.

## CI Coverage

GitHub Actions runs backend quality, backend integration, frontend quality, and Docker validation on pull requests, pushes to `main`, and manual dispatch. Backend integration uses a real Docker Compose stack, fails on unexpected integration skips, prints Compose diagnostics on failure, and tears down CI volumes. CI-only host access settings remain under `WORKFLOWFORGE_TEST_*`.

Dependabot checks GitHub Actions, Python dependencies, frontend dependencies, and Docker images weekly in practical groups.

## Known Limitations

- No authentication, authorization, users, tenants, or RBAC.
- No document upload, extraction, OCR, classification, or metadata model.
- No workflow definitions, workflow execution engine, retries, reviews, or business scheduler triggers.
- No AI provider integration, prompts, structured AI outputs, or evaluation runner.
- No reports, notifications, billing, production deployment, Kubernetes, image publishing, or release automation.
- The frontend is an operational status view, not final product branding or a workflow dashboard.
- The baseline migration intentionally creates only Alembic metadata and no business tables.

## Phase 2 Boundary

Phase 2 should begin product behavior. Candidate work includes the first durable domain model, document intake boundaries, workflow definition and execution slices, authentication planning, API versioned product routes, and operator UI beyond system health. Phase 2 should preserve the Phase 1 boundaries rather than bypassing them.

## Release-Candidate Status

`v0.1.0-alpha.1` is ready to tag after this readiness audit is merged, local validation passes, and GitHub Actions remain green on the release branch. Do not create the tag or GitHub release as part of this step.

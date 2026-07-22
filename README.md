# WorkflowForge

WorkflowForge is an open-source operations platform for building, evaluating, and running reliable AI-assisted workflows across documents, APIs, browser automation, human approvals, and external systems.

## Project Status

WorkflowForge has completed the Phase 2 identity, tenancy, security, audit, and operator-auth foundation on `feature/identity-tenancy-security`. The repository now has the Phase 1 platform base plus document metadata persistence, durable identity state, authentication/session lifecycle, tenant-context authorization, security audit logging, Redis rate limiting, session cleanup, first-owner bootstrap, and a React operator shell for login, organization selection, status, and tenant-context diagnostics.

Still deferred: public registration, password reset, MFA, email verification, membership and organization administration UI, audit dashboards, SIEM/export, document upload, document tenancy migration, workflow execution, and Phase 3 features.

## Current Capabilities

- Modular monolith workspace with FastAPI API, Celery worker, Celery Beat scheduler, React/Vite web app, PostgreSQL, Redis, and MinIO.
- Document metadata domain and PostgreSQL persistence.
- User, organization, membership, role, permission, and tenant-context domain/application foundations.
- Argon2 password credentials, HS256 JWT bearer access tokens, durable sessions, rotating refresh tokens, replay detection, logout, and logout-all.
- HttpOnly refresh cookies, readable CSRF double-submit cookie, Origin validation, security headers, and production configuration validation.
- `workflowforge-bootstrap-owner` first-owner CLI with PostgreSQL advisory locking and audit evidence.
- Redis-backed login/refresh rate limiting with development fail-open and production fail-closed validation.
- Durable append-only security audit events with same-transaction success events and independent failure/denial events.
- Tenant-scoped permission dependencies under `/api/v1/organizations/{organization_id}/...`.
- React login/session restoration, in-memory access token, active organization selection, guarded routes, permission-aware shell, and safe error handling.

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

## Local Start

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Open:

```text
http://127.0.0.1:5173/status
http://127.0.0.1:5173/login
```

For a clean local owner account, run migrations and bootstrap:

```powershell
uv run alembic upgrade head
$env:WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD='change-this-demo-password'
uv run workflowforge-bootstrap-owner --email owner@example.com --display-name "Owner" --organization-name "Example" --organization-slug example --password-from-env
Remove-Item Env:\WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD
```

Use demo-only credentials locally and keep real secrets out of tracked files.

## Repository Map

```text
.github/               CI workflows, issue templates, and PR template.
apps/                  Runnable API, worker, scheduler, and web processes.
packages/              Domain, application, infrastructure, and contract layers.
integrations/          Integration-specific adapters and notes.
examples/              Small examples for future users and contributors.
demo_data/             Non-secret sample data for demos and tests.
tests/                 Unit, architecture, integration, and system test areas.
migrations/            Alembic migration workspace.
docs/                  Architecture records, proof docs, and runbooks.
infrastructure/        Deployment and operations assets.
scripts/               Developer and automation scripts.
```

## Documentation

- [Product definition](docs/product.md)
- [V1 scope](docs/v1-scope.md)
- [Architecture](docs/architecture.md)
- [Identity](docs/identity.md)
- [Tenancy](docs/tenancy.md)
- [Authorization](docs/authorization.md)
- [Security](docs/security.md)
- [Audit](docs/audit.md)
- [Phase 2 security proof](docs/phase-2-security-proof.md)
- [Phase 2 release notes](docs/phase-2-release-notes.md)
- [Phase 2 demo runbook](docs/phase-2-demo-runbook.md)
- [Phase 1 alpha readiness](docs/phase-1-readiness.md)
- [ADRs](docs/adr/README.md)
- [Glossary](docs/glossary.md)

## Backend Workspace

The Python backend uses Python 3.12, `uv`, and editable workspace packages:

```powershell
uv sync --all-packages --group dev
uv run python scripts/validate_architecture.py
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages migrations scripts tests
uv run pytest -m "not integration"
uv run pytest tests/integration/api -v
uv run pytest tests/integration/database -v
uv run pytest tests/integration/redis -v
```

Database migration commands:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade 0006_sessions
uv run alembic upgrade head
```

Expected Phase 2 head is `0007_security_audit_events`. `uv run alembic check` currently reports known pre-existing metadata drift for unique/index modeling and one audit JSON default; see [Security](docs/security.md).

## Frontend Workspace

The frontend uses React, TypeScript, Vite, React Router, TanStack Query, Zod, Vitest, Testing Library, ESLint, Prettier, and pnpm:

```powershell
corepack pnpm --dir apps/web install --frozen-lockfile
corepack pnpm --dir apps/web format:check
corepack pnpm --dir apps/web lint
corepack pnpm --dir apps/web typecheck
corepack pnpm --dir apps/web test:run
corepack pnpm --dir apps/web build
```

Public Vite settings:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_CSRF_COOKIE_NAME=workflowforge_csrf
VITE_CSRF_HEADER_NAME=X-CSRF-Token
```

Do not put backend secrets, database URLs, Redis URLs, object-storage credentials, API keys, access tokens, or refresh tokens in Vite variables.

## Health And Operations

API health endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health/dependencies`

Dependency health checks PostgreSQL, Redis, object storage, worker availability, and scheduler heartbeat. The React `/status` route uses these endpoints and remains public. Authenticated operator pages live under `/app`.

Stop local services with:

```powershell
docker compose down
```

Use `docker compose down -v` only for a destructive reset; it deletes local PostgreSQL, Redis, and MinIO development data.

## CI

GitHub Actions runs backend quality/integration, frontend quality/build, and Docker validation workflows on pull requests, pushes to `main`, and manual dispatch. Docker validation renders Compose config and builds the shared backend image used by API, migrations, worker, and scheduler; the frontend workflow performs the production web build.

## Versioning

Phase 1 used `v0.1.0-alpha.1`. The recommended Phase 2 tag after merge is `v0.2.0-alpha.1`; do not create the tag until the final Phase 2 PR is merged and CI is green on the release branch.

## Contributing

WorkflowForge is not yet ready for broad external contribution. Early contributions should be small, focused, and aligned with the architecture boundaries in this repository. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/commits.md](docs/commits.md).

## License

WorkflowForge is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

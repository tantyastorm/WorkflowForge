# Phase 3 Release Notes

WorkflowForge Phase 3 adds the document intake and storage foundation that later workflow automation will build on.

## Added

- Tenant-scoped document list, detail, version, artifact, archive, and short-lived download URL APIs.
- Multipart document upload with validation, object-storage handoff, idempotency keys, duplicate detection, and safe metadata responses.
- Batch domain, PostgreSQL tables, repository, service, API routes, role permissions, audit events, and React operator page.
- Case domain, PostgreSQL tables, repository, service, API routes, role permissions, audit events, and React operator page for documents, comments, tasks, decisions, close/reopen, and archive.
- Document operational Celery task registrations for expired upload-idempotency cleanup, stale temp-object cleanup hooks, and pending-storage reconciliation hooks.
- Alembic migrations `0010_batches` and `0011_cases`.

## Deferred

- OCR, AI classification, extraction, workflow execution, review queues, approval routing, and human-in-the-loop workflow orchestration remain out of Phase 3 scope.
- Batch and case screens are functional operator surfaces, not final product branding.

## Validation

Run the standard backend and frontend checks before release:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages migrations tests
uv run python scripts\validate_architecture.py
uv run alembic check
uv run pytest -m "not integration" -q
uv run pytest -m integration -q
uv run pytest --cov --cov-report=term-missing -q
corepack pnpm --dir apps\web lint
corepack pnpm --dir apps\web typecheck
corepack pnpm --dir apps\web test:run
corepack pnpm --dir apps\web build
```

`uv run alembic check` and integration tests require a correctly configured local PostgreSQL, Redis, MinIO, API, worker, and scheduler environment.

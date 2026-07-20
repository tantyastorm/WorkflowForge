# Worker App

Belongs here: the background worker process entry point, task execution wiring, queue consumer composition, and worker-specific startup concerns.

Does not belong here: domain rules, API routes, scheduler triggers, frontend code, or provider-specific implementations outside composition.

Owner: `apps/worker` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring.

Python workspace distribution: `workflowforge-worker`.

## Process

The worker is a Celery worker process inside the modular monolith, not a microservice. It uses the shared backend image in Docker Compose and consumes the configured default and diagnostic queues.

Run from the repository root:

```powershell
uv run celery -A workflowforge_worker.main:app worker --loglevel=INFO
```

Phase 1 registers only safe diagnostic tasks. No workflow, document, AI, browser, notification, or business tasks exist yet. Future task bodies should remain transport adapters that invoke application use cases instead of carrying business orchestration directly.

## Diagnostic Task

`system.diagnostics.echo` accepts a bounded JSON payload:

```json
{"message": "hello"}
```

It returns the echoed message, task ID, task name, UTC processed timestamp, worker identifier, and optional correlation ID from task headers. It performs no filesystem access, external calls, or arbitrary code execution.

Run a bounded diagnostic call against a running worker:

```powershell
uv run python scripts/run_diagnostic_task.py --message hello --timeout 10
```

Worker availability is reported by the API dependency health endpoint through a bounded Celery inspect ping. The response reports whether at least one worker answered and does not expose broker URLs or internal worker node names.

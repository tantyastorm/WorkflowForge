# Scheduler App

Belongs here: the scheduler process entry point, scheduled workflow trigger wiring, and scheduler-specific startup concerns.

Does not belong here: domain rules, API routes, worker task bodies, frontend code, or provider-specific implementations outside composition.

Owner: `apps/scheduler` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring.

Python workspace distribution: `workflowforge-scheduler`.

## Process

The scheduler is a Celery Beat process inside the modular monolith, not a microservice. It publishes periodic diagnostic work and must not execute workflow business logic directly.

Run from the repository root:

```powershell
uv run celery -A workflowforge_scheduler.main:app beat --loglevel=INFO
```

Docker Compose stores the Beat state file in `/tmp/workflowforge-celerybeat-schedule` inside the container so scheduler runtime files are not written into the repository.

## Heartbeat

Celery Beat schedules `system.diagnostics.scheduler_heartbeat`. The task writes the current UTC timestamp to Redis key `workflowforge:diagnostics:scheduler:last_seen` with a TTL. This is transient operational visibility, not durable workflow state.

Scheduler health is reported by reading that heartbeat key and checking that the timestamp is present, parseable, and still within the configured TTL. A running container alone is not treated as scheduler health.

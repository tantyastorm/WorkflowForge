# Scheduler App

Belongs here: the future scheduler process entry point, scheduled workflow trigger wiring, and scheduler-specific startup concerns.

Does not belong here: domain rules, API routes, worker task bodies, frontend code, or provider-specific implementations outside composition.

Owner: `apps/scheduler` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring. Runtime code is not implemented yet.

# Worker App

Belongs here: the future background worker process entry point, task execution wiring, queue consumer composition, and worker-specific startup concerns.

Does not belong here: domain rules, API routes, scheduler triggers, frontend code, or provider-specific implementations outside composition.

Owner: `apps/worker` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring. Runtime code is not implemented yet.

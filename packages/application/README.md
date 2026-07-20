# Application Package

Belongs here: use cases, orchestration, ports, command handling, workflow coordination, and application-level policies.

Does not belong here: framework entry points, database implementations, external service clients, frontend code, or provider-specific adapters.

Owner: application layer.

Dependency direction: may depend on `packages/domain` and `packages/contracts`. It must not depend directly on `packages/infrastructure`.

Python workspace distribution: `workflowforge-application`.

# API App

Belongs here: the future backend API process entry point, HTTP routing composition, request adapters, and API-specific wiring.

Does not belong here: domain rules, infrastructure implementations, worker jobs, scheduler logic, or frontend code.

Owner: `apps/api` process composition root.

Dependency direction: may depend on `packages/application`, `packages/contracts`, and infrastructure adapters only through composition wiring. Runtime code is not implemented yet.

# Contracts Package

Belongs here: stable shared contracts, ports, commands, events, task payloads, and transport-neutral DTOs.

Does not belong here: framework-specific request handlers, ORM models, external SDK clients, business rule implementations, or process startup code.

Owner: shared contract layer.

Dependency direction: should remain stable and transport-neutral so apps, application services, and infrastructure adapters can share boundaries without coupling to runtime frameworks.

Python workspace distribution: `workflowforge-contracts`.

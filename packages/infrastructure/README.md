# Infrastructure Package

Belongs here: implementations for persistence, queues, storage, browser automation, AI provider clients, and external system adapters.

Does not belong here: domain rules, application use case definitions, frontend code, or process entry points.

Owner: infrastructure adapter layer.

Dependency direction: implements ports defined by inner layers and may depend on `packages/domain` and `packages/contracts`. Apps compose these adapters with application services.

Python workspace distribution: `workflowforge-infrastructure`.

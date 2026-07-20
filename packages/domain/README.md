# Domain Package

Belongs here: core WorkflowForge business concepts, invariants, policies, and pure domain behavior.

Does not belong here: framework code, database access, queues, HTTP clients, browser automation clients, AI provider SDKs, or process startup code.

Owner: inner domain layer.

Dependency direction: must remain independent of application frameworks and infrastructure. It may use stable contracts only when those contracts are domain-neutral.

Python workspace distribution: `workflowforge-domain`.

# ADR 0001: Adopt a modular monolith with separate runtime processes

- Status: Accepted
- Date: 2026-07-20

## Context

WorkflowForge V1 has broad product scope: durable workflow definitions, executions, step attempts, human review, document and artifact storage, AI-assisted processing, external integrations, browser automation, evaluation, and operational visibility.

The project starts with one primary development team and needs rapid implementation without losing architectural discipline. Workflows must survive process restarts, background execution must be reliable, and the system should be production-relevant while remaining approachable for local development.

There is not yet evidence that microservices are justified. Service boundaries, scaling needs, team ownership, and failure domains should be proven by product behavior before becoming network boundaries.

## Decision

WorkflowForge will use a modular monolith with one repository, one coordinated release, separate API, worker, scheduler, and frontend processes, and shared internal packages with enforced dependency direction.

PostgreSQL is the source of truth for durable workflow state. Redis and S3-compatible object storage are supporting infrastructure: Redis for queues and transient coordination, object storage for documents and artifacts.

## Decision Details

The repository is organized around app composition roots and internal packages:

- `apps/api` wires HTTP transport to application use cases and infrastructure adapters.
- `apps/worker` consumes queued work and invokes application use cases.
- `apps/scheduler` publishes scheduled work and coordinates periodic tasks.
- `apps/web` provides the React operator console.
- `packages/domain` contains core business rules and state transition semantics.
- `packages/application` contains use cases and orchestration.
- `packages/contracts` contains stable ports, commands, events, task payloads, DTOs, and provider-neutral boundaries.
- `packages/infrastructure` implements adapters for concrete systems.

Composition roots may depend on both application and infrastructure packages because they connect ports to implementations. Inner layers must not depend on infrastructure or apps.

## Why Workers Are Separate Processes

Workers are separate runtime processes because workflow execution includes asynchronous and long-running work. They need independent concurrency settings, fault isolation from HTTP request handling, separate restart behavior, queue consumption, and future process-level scaling.

The scheduler is also separate from task execution so periodic publication and background work can have different lifecycles.

This separation does not create microservices. The processes remain part of one coordinated product and release, using shared internal packages and one durable source of truth.

## Why Microservices Are Not Justified Initially

Microservices are not selected for V1 because there is no demonstrated independent scaling need, no separate team ownership, and no stable service boundaries proven by behavior.

Starting with network boundaries would increase local development cost, deployment complexity, observability burden, and distributed failure modes. Distributed transactions would increase risk for durable workflows. Internal package boundaries provide enough separation for the current stage.

## Clean Boundaries and Future Extraction

Ports and adapters, stable contracts, isolated modules, composition roots, architecture tests, and durable integration events where later needed can keep extraction possible.

Extraction should not be described as effortless. Moving a module into a service would still require operational ownership, API contracts, data ownership decisions, deployment work, monitoring, and failure-mode design.

## Alternatives Considered

### Unstructured Monolith

Rejected because framework and domain concerns would mix, background work would become harder to reason about, testing boundaries would weaken, and future change costs would rise.

### Microservices from the Start

Rejected because the operational cost is excessive for the current evidence. It would introduce premature network boundaries, distributed failure modes, harder local development, and unclear ownership and scaling assumptions.

### Serverless Functions

Rejected as the primary architecture because WorkflowForge needs long-running workflows, durable orchestration, local reproducibility, background workers, browser automation, and process control. Cold starts and execution limits also create risk for the core workload.

Serverless adapters may still be useful for isolated integrations later.

### External Workflow Engine from the Start

Temporal, Prefect, and similar systems are strong tools for some workflow problems. They are not selected initially because they add operational and conceptual weight before WorkflowForge has proven its execution semantics.

V1 can establish durable execution with PostgreSQL, workers, explicit state transitions, and bounded retries. The decision can be revisited when requirements justify a dedicated workflow engine.

## Consequences

WorkflowForge will have coordinated deployments and a single database initially. Strict package-boundary enforcement is required. Shared code is easy to use, but it must not become uncontrolled coupling.

Workers can scale separately at the process level. Module extraction remains possible but non-trivial. Operational simplicity is prioritized over maximum independent scalability.

## Positive Consequences

- Simpler deployment and operations.
- Clear local development path.
- Consistent transactions around durable workflow state.
- Easier refactoring while product behavior is still evolving.
- Background work can be scaled separately from HTTP handling.
- Package boundaries make dependencies visible without adding network calls.

## Negative Consequences

- Package boundaries must be enforced through discipline and tests.
- Process releases remain coordinated.
- Independent scaling is limited compared with microservices.
- A single database can become a contention point if ownership stays unclear.
- Careless imports can erode the architecture over time.

## Risks and Mitigations

- Risk: application code imports infrastructure directly. Mitigation: architecture tests and code review.
- Risk: shared contracts become a dumping ground. Mitigation: keep HTTP schemas, database models, and frontend-only types in their owning layers.
- Risk: workers accumulate business logic. Mitigation: workers invoke application use cases and keep task bodies thin.
- Risk: Redis is treated as workflow state. Mitigation: PostgreSQL remains the durable source of truth.
- Risk: modules become too large. Mitigation: introduce modules or bounded contexts only when product behavior supports them.

## Conditions for Revisiting

Revisit this decision if one module requires materially different scaling, deployment cadence conflicts emerge, security isolation requires a process or network boundary, a separate team owns a stable module, failure isolation cannot be achieved adequately, a workflow engine becomes necessary due to execution complexity, or database contention and ownership become problematic.

## Related Documentation

- [Architecture](../architecture.md)
- [V1 scope](../v1-scope.md)
- [Glossary](../glossary.md)

# WorkflowForge

WorkflowForge is an open-source operations platform for building, evaluating, and running reliable AI-assisted workflows across documents, APIs, browser automation, human approvals, and external systems.

## Project Status

WorkflowForge is in early Phase 1 repository foundation work. The project is defining its repository layout, contribution standards, and architecture boundaries before runtime code is introduced.

This commit does not implement runtime setup, application code, package configuration, Docker services, database migrations, frontend tooling, or workflow execution features.

## Planned Capabilities

- Workflow authoring and execution across documents, APIs, browser tasks, and external systems.
- Human approval checkpoints for sensitive operations.
- Evaluation support for reliability, repeatability, and regression detection.
- Operational visibility into workflow runs, task outcomes, and integration behavior.
- Modular integration points for AI providers, queues, storage, browser automation, and third-party systems.

## Architecture Direction

WorkflowForge V1 is planned as a modular monolith with independently runnable processes:

- `apps/api` exposes the backend API process.
- `apps/worker` runs background workflow and task execution.
- `apps/scheduler` coordinates scheduled work.
- `apps/web` contains the React frontend.

Core behavior is organized by dependency direction:

```text
apps/api
apps/worker
apps/scheduler
        |
        v
packages/application
        |
        +-- packages/domain
        +-- packages/contracts

packages/infrastructure
        +-- packages/domain
        +-- packages/contracts
```

The domain layer remains independent of frameworks and infrastructure. Application orchestration depends on domain and contracts, but not directly on infrastructure. Infrastructure implements ports and adapters defined by the inner layers. Apps are composition roots that wire processes together.

## Repository Map

```text
.github/               Issue and pull request templates.
apps/                  Runnable process entry points.
packages/              Domain, application, infrastructure, and contract layers.
integrations/          Integration-specific adapters and notes.
examples/              Small examples for future users and contributors.
demo_data/             Non-secret sample data for demos and tests.
tests/                 Architecture, integration, and system test areas.
migrations/            Future database migration workspace.
docs/                  Architecture records and repository documentation.
infrastructure/        Deployment and operations assets.
scripts/               Developer and automation scripts.
```

## Phase 1 Scope

Current Phase 1 work is limited to repository structure, documentation, contribution practices, and architecture boundary definitions. Runtime implementation will be introduced in later focused commits.

## Contributing

WorkflowForge is not yet ready for broad external contribution. Early contributions should be small, focused, and aligned with the architecture boundaries in this repository. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/commits.md](docs/commits.md).

## License

WorkflowForge is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

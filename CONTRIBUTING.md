# Contributing to WorkflowForge

WorkflowForge is in early repository foundation work. Contributions should stay focused, easy to review, and aligned with the planned modular monolith architecture.

## Branches

Use short, descriptive branch names:

- `feat/<area>-<change>`
- `fix/<area>-<bug>`
- `docs/<topic>`
- `chore/<maintenance-topic>`

## Commits

Use Conventional Commits. Supported types are documented in [docs/commits.md](docs/commits.md).

Keep commits focused on one concern. Avoid mixing feature work, formatting churn, dependency updates, and documentation edits unless they are part of the same intentional change.

## Tests

Add or update tests alongside behavior changes. Place architecture boundary tests in `tests/architecture`, integration tests in `tests/integration`, and end-to-end process tests in `tests/system` as those suites are introduced.

## Secrets and Configuration

Never commit secrets, credentials, tokens, private keys, local database files, or personal environment files. Use `.env.example` only for non-secret configuration documentation.

## Architecture Boundaries

- `packages/domain` must remain independent of frameworks and infrastructure.
- `packages/application` may depend on `packages/domain` and `packages/contracts`.
- `packages/application` must not depend directly on `packages/infrastructure`.
- `packages/infrastructure` implements adapters for ports defined by inner layers.
- `apps/*` are composition roots for runnable processes.

## Pull Requests

Pull requests should include a clear summary, motivation, test evidence, and any architecture, migration, configuration, or documentation impact. Keep unrelated formatting changes out of feature and fix pull requests.

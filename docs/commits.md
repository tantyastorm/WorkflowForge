# Commit Convention

WorkflowForge uses Conventional Commits to keep history searchable and release notes practical.

## Format

```text
type(scope): short imperative summary
```

Use a body when it helps explain motivation, trade-offs, or migration notes.

## Supported Types

- `feat`: user-facing or platform capability.
- `fix`: bug fix.
- `test`: test-only change.
- `refactor`: behavior-preserving code restructuring.
- `docs`: documentation-only change.
- `chore`: repository maintenance.
- `perf`: performance improvement.
- `build`: build system, dependencies, or packaging.
- `ci`: continuous integration configuration.

## Examples

```text
chore(repo): establish WorkflowForge monorepo foundation
docs(adr): record modular monolith architecture direction
feat(api): add workflow run creation endpoint
fix(worker): retry transient document extraction failures
test(architecture): enforce application layer import boundaries
ci(python): run backend checks on pull requests
build(web): add frontend package workspace
```

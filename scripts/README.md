# Scripts

Belongs here: future developer, maintenance, validation, and automation scripts.

Does not belong here: runtime application logic, business workflows, secrets, or one-off local scratch files.

Owner: developer experience and repository automation.

Dependency direction: scripts may call public project tooling once it exists. They should not become hidden application entry points.

## Architecture Validation

Run import-boundary validation from the repository root:

```powershell
uv run python scripts/validate_architecture.py
```

The validator statically inspects Python imports under `apps/*/src/` and `packages/*/src/`, enforces the documented package dependency rules, and detects WorkflowForge package cycles.

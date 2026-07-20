# Architecture Tests

Belongs here: tests that enforce dependency direction, import boundaries, layering rules, and repository structure.

Does not belong here: business workflow scenarios, external service integration tests, or full system tests.

Owner: architecture quality gates.

Dependency direction: these tests inspect the codebase and should not require production services.

## Import Boundaries

Architecture tests enforce the modular monolith package boundaries documented in `docs/architecture.md`, ADR 0001, and the package README files.

Run validation directly with:

```powershell
uv run python scripts/validate_architecture.py
```

The same validation is integrated into Pytest, so `uv run pytest` fails when current source imports violate package boundaries.

When architecture rules change, update the documentation first. Material architecture changes require a superseding ADR or an explicit ADR status change, then the validator rules and tests can be updated to match.

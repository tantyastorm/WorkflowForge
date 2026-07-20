# Tests

Belongs here: automated checks for the Python workspace and, later, implemented WorkflowForge behavior.

Unit tests live in `tests/unit`. Architecture, integration, and system tests keep their existing ownership boundaries as implementation grows.

Run the current backend checks with:

```powershell
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

Database integration tests require real PostgreSQL settings:

```powershell
uv run pytest -m "not integration"
uv run pytest -m integration
```

# Tests

Belongs here: automated checks for the Python workspace and, later, implemented WorkflowForge behavior.

Unit tests live in `tests/unit`. Architecture, integration, and system tests keep their existing ownership boundaries as implementation grows.

Run the current backend checks with:

```powershell
uv run python scripts/validate_architecture.py
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages migrations scripts tests
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

Database integration tests require real PostgreSQL settings:

```powershell
uv run pytest -m "not integration"
uv run pytest -m integration
```

CI runs integration tests against the real Docker Compose platform: PostgreSQL, Redis, MinIO, API, migrations, worker, and scheduler. The CI integration job fails if any integration test skips because a required service is missing. The coverage threshold is defined in `pyproject.toml` and currently requires at least 80% total coverage.

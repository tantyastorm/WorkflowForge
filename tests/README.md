# Tests

Belongs here: automated checks for the Python workspace and, later, implemented WorkflowForge behavior.

Unit tests live in `tests/unit`. Architecture, integration, and system tests keep their existing ownership boundaries as implementation grows.

Run the current backend checks with:

```powershell
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

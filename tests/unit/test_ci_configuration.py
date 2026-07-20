"""Static checks for repository CI configuration."""

from pathlib import Path

WORKFLOWS = Path(".github/workflows")
DEPENDABOT = Path(".github/dependabot.yml")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_workflow_files_exist() -> None:
    assert (WORKFLOWS / "backend.yml").is_file()
    assert (WORKFLOWS / "frontend.yml").is_file()
    assert (WORKFLOWS / "docker.yml").is_file()


def test_workflows_use_minimal_permissions_and_concurrency() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        text = _read(workflow)
        assert "permissions:\n  contents: read" in text
        assert "concurrency:" in text
        assert "cancel-in-progress: true" in text
        assert "continue-on-error" not in text


def test_backend_workflow_runs_required_quality_commands() -> None:
    backend = _read(WORKFLOWS / "backend.yml")

    for command in [
        "uv sync --all-packages --group dev --frozen",
        "uv run python scripts/validate_architecture.py",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy apps packages migrations scripts tests",
        'uv run pytest -m "not integration"',
        "uv run pytest --cov --cov-report=term-missing",
    ]:
        assert command in backend


def test_integration_workflow_uses_compose_and_fails_on_skips() -> None:
    backend = _read(WORKFLOWS / "backend.yml")

    assert "docker compose up --build -d" in backend
    assert "uv run pytest -m integration -rA" in backend
    assert "Integration tests skipped unexpectedly in CI." in backend
    assert "docker compose logs api worker scheduler migrate minio-init" in backend
    assert "docker compose down -v" in backend


def test_frontend_workflow_uses_corepack_and_frozen_pnpm_install() -> None:
    frontend = _read(WORKFLOWS / "frontend.yml")

    for command in [
        "corepack enable",
        "require('./apps/web/package.json').packageManager",
        "corepack pnpm --dir apps/web install --frozen-lockfile",
        "corepack pnpm --dir apps/web format:check",
        "corepack pnpm --dir apps/web lint",
        "corepack pnpm --dir apps/web typecheck",
        "corepack pnpm --dir apps/web test:run",
        "corepack pnpm --dir apps/web build",
    ]:
        assert command in frontend


def test_docker_workflow_validates_compose_and_shared_backend_image() -> None:
    docker = _read(WORKFLOWS / "docker.yml")

    assert "docker compose config" in docker
    assert "docker compose build api" in docker
    assert "api, worker, scheduler, and migrate services" in docker
    assert "docker/login-action" not in docker
    assert "docker/build-push-action" not in docker


def test_dependabot_covers_current_ecosystems_without_auto_merge() -> None:
    dependabot = _read(DEPENDABOT)

    for ecosystem in ["github-actions", "pip", "npm", "docker"]:
        assert f"package-ecosystem: {ecosystem}" in dependabot
    assert "directory: /apps/web" in dependabot
    assert "interval: weekly" in dependabot
    assert "auto-merge" not in dependabot.lower()

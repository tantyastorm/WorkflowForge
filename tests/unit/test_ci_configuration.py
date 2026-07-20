"""Static checks for repository CI configuration."""

from pathlib import Path

WORKFLOWS = Path(".github/workflows")
DEPENDABOT = Path(".github/dependabot.yml")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _backend_integration_job() -> str:
    backend = _read(WORKFLOWS / "backend.yml")
    return backend.split("  integration:", maxsplit=1)[1]


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

    assert "docker compose -f docker-compose.yml -f docker-compose.ci.yml up --build -d" in backend
    assert "uv run pytest -m integration -rA" in backend
    assert "Integration tests skipped unexpectedly in CI." in backend
    assert (
        "docker compose -f docker-compose.yml -f docker-compose.ci.yml "
        "logs api worker scheduler migrate minio-init"
    ) in backend
    assert "docker compose -f docker-compose.yml -f docker-compose.ci.yml down -v" in backend
    assert "WORKFLOWFORGE_TEST_API_BASE_URL" in backend
    assert "WORKFLOWFORGE_TEST_DATABASE_HOST_PORT" in backend
    assert "WORKFLOWFORGE_TEST_S3_ENDPOINT_URL" in backend


def test_integration_workflow_keeps_host_ports_out_of_app_settings_namespace() -> None:
    backend = _read(WORKFLOWS / "backend.yml")

    forbidden_settings = [
        "WORKFLOWFORGE_API_HOST_PORT",
        "WORKFLOWFORGE_REDIS_HOST_PORT",
        "WORKFLOWFORGE_POSTGRES_HOST_PORT",
        "WORKFLOWFORGE_MINIO_API_HOST_PORT",
        "WORKFLOWFORGE_MINIO_CONSOLE_HOST_PORT",
    ]
    for setting in forbidden_settings:
        assert setting not in backend


def test_integration_workflow_scopes_compose_app_settings_away_from_pytest_env() -> None:
    integration_job = _backend_integration_job()

    integration_env = integration_job.split("    env:", maxsplit=1)[1].split(
        "    steps:", maxsplit=1
    )[0]
    for setting in [
        "WORKFLOWFORGE_DATABASE_PASSWORD",
        "WORKFLOWFORGE_S3_ACCESS_KEY",
        "WORKFLOWFORGE_S3_SECRET_KEY",
        "WORKFLOWFORGE_S3_BUCKET",
        "WORKFLOWFORGE_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS",
        "WORKFLOWFORGE_SCHEDULER_HEARTBEAT_TTL_SECONDS",
    ]:
        assert setting not in integration_env

    for setting in [
        "WORKFLOWFORGE_TEST_DATABASE_PASSWORD",
        "WORKFLOWFORGE_TEST_S3_ACCESS_KEY",
        "WORKFLOWFORGE_TEST_S3_SECRET_KEY",
        "WORKFLOWFORGE_TEST_S3_BUCKET",
    ]:
        assert setting in integration_env


def test_backend_quality_job_is_isolated_from_integration_environment() -> None:
    backend = _read(WORKFLOWS / "backend.yml")

    quality_job = backend.split("  quality:", maxsplit=1)[1].split("  integration:", maxsplit=1)[0]
    assert "WORKFLOWFORGE_TEST_" not in quality_job
    assert "docker-compose.ci.yml" not in quality_job


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

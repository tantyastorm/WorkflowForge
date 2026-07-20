"""Static checks for local Docker Compose configuration."""

from pathlib import Path

import pytest

COMPOSE_FILE = Path("docker-compose.yml")


def _compose_text() -> str:
    return COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "service",
    ["postgres", "redis", "minio", "minio-init", "migrate", "api", "worker", "scheduler"],
)
def test_required_compose_services_exist(service: str) -> None:
    assert f"  {service}:" in _compose_text()


def test_compose_file_does_not_use_latest_images() -> None:
    assert ":latest" not in _compose_text()


@pytest.mark.parametrize("volume", ["postgres_data", "redis_data", "minio_data"])
def test_required_named_volumes_exist(volume: str) -> None:
    assert f"  {volume}:" in _compose_text()


def test_api_waits_for_migrations_and_infrastructure() -> None:
    compose = _compose_text()

    assert "migrate:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "condition: service_healthy" in compose
    assert 'uv", "run", "alembic", "upgrade", "head"' in compose


def test_health_checks_are_configured() -> None:
    compose = _compose_text()

    assert "pg_isready" in compose
    assert "redis-cli ping | grep PONG" in compose
    assert 'mc", "ready", "local"' in compose
    assert "/health/ready" in compose
    assert "celery -A workflowforge_worker.main:app inspect ping" in compose
    assert "WORKFLOWFORGE_SCHEDULER_HEARTBEAT_KEY" in compose


def test_worker_and_scheduler_use_backend_image_with_separate_commands() -> None:
    compose = _compose_text()

    assert "workflowforge_worker.main:app" in compose
    assert "workflowforge_scheduler.main:app" in compose
    assert '"worker",' in compose
    assert '"beat",' in compose
    assert "/tmp/workflowforge-celerybeat-schedule" in compose

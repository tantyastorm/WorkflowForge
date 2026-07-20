"""Process health endpoint tests."""

from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_infrastructure.config import Environment, Settings


def test_liveness_returns_ok_without_dependency_checks() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_readiness_returns_ready_during_active_lifespan() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "api"}


def test_readiness_returns_503_when_startup_has_not_completed() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "api"}


def test_shutdown_resets_readiness() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app):
        assert app.state.readiness.ready is True

    assert app.state.readiness.ready is False


def test_readiness_state_belongs_to_each_app_instance() -> None:
    first = create_app(Settings(environment=Environment.TEST))
    second = create_app(Settings(environment=Environment.TEST))

    with TestClient(first):
        assert first.state.readiness.ready is True
        assert second.state.readiness.ready is False

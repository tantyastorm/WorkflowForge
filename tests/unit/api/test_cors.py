"""CORS behavior tests."""

from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_infrastructure.config import Environment, Settings


def test_configured_origin_receives_cors_headers() -> None:
    app = create_app(
        Settings(environment=Environment.TEST, cors_origins=("http://localhost:5173",))
    )

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_loopback_frontend_origin_receives_cors_headers() -> None:
    app = create_app(
        Settings(environment=Environment.TEST, cors_origins=("http://127.0.0.1:5173",))
    )

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_unknown_origin_does_not_receive_cors_headers() -> None:
    app = create_app(
        Settings(environment=Environment.TEST, cors_origins=("http://localhost:5173",))
    )

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "http://unknown.local"})

    assert "access-control-allow-origin" not in response.headers

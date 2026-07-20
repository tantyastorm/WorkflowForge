"""OpenAPI behavior tests."""

from fastapi.testclient import TestClient
from workflowforge_api import __version__
from workflowforge_api.factory import create_app
from workflowforge_infrastructure.config import ApiSettings, Environment, Settings


def test_openapi_metadata_and_health_routes_are_registered() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "WorkflowForge API"
    assert schema["info"]["version"] == __version__
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/health/dependencies" in schema["paths"]
    assert "/health/worker" not in schema["paths"]


def test_openapi_is_not_served_when_docs_are_disabled() -> None:
    app = create_app(Settings(environment=Environment.TEST, api=ApiSettings(docs_enabled=False)))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 404

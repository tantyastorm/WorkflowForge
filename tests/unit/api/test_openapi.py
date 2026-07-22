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
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/refresh" in schema["paths"]
    assert "/api/v1/auth/me" in schema["paths"]
    assert "/api/v1/auth/organizations" in schema["paths"]
    context_path = "/api/v1/organizations/{organization_id}/tenancy/context"
    probe_path = "/api/v1/organizations/{organization_id}/tenancy/authorized-probe"
    assert context_path in schema["paths"]
    assert probe_path in schema["paths"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/api/v1/auth/organizations"]["get"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/api/v1/auth/logout"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/api/v1/auth/logout-all"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"][context_path]["get"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"][probe_path]["get"]["security"] == [{"HTTPBearer": []}]
    organization_parameter = schema["paths"][context_path]["get"]["parameters"][0]
    assert organization_parameter["name"] == "organization_id"
    assert organization_parameter["in"] == "path"
    assert organization_parameter["required"] is True
    assert organization_parameter["schema"]["format"] == "uuid"
    assert all(
        parameter["in"] != "header"
        for parameter in schema["paths"][context_path]["get"]["parameters"]
    )
    assert "system probe" in schema["paths"][context_path]["get"]["summary"].casefold()
    assert "system probe" in schema["paths"][probe_path]["get"]["summary"].casefold()
    assert "401" in schema["paths"][context_path]["get"]["responses"]
    assert "403" in schema["paths"][context_path]["get"]["responses"]
    assert "401" in schema["paths"][probe_path]["get"]["responses"]
    assert "403" in schema["paths"][probe_path]["get"]["responses"]
    assert "requestBody" not in schema["paths"]["/api/v1/auth/refresh"]["post"]
    assert "requestBody" not in schema["paths"]["/api/v1/auth/organizations"]["get"]
    assert "requestBody" not in schema["paths"][context_path]["get"]
    assert "requestBody" not in schema["paths"][probe_path]["get"]
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    assert login_schema["properties"]["password"]["format"] == "password"
    assert login_schema["properties"]["password"]["writeOnly"] is True
    token_properties = schema["components"]["schemas"]["TokenResponse"]["properties"]
    assert "refresh_token" not in token_properties
    assert "/health/worker" not in schema["paths"]


def test_openapi_is_not_served_when_docs_are_disabled() -> None:
    app = create_app(Settings(environment=Environment.TEST, api=ApiSettings(docs_enabled=False)))

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 404

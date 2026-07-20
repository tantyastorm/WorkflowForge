"""FastAPI application factory tests."""

from typing import Any

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_infrastructure.config import ApiSettings, Environment, Settings


def test_multiple_app_instances_have_independent_state() -> None:
    first = create_app(Settings(environment=Environment.TEST))
    second = create_app(Settings(environment=Environment.TEST))

    assert first is not second
    assert first.state.readiness is not second.state.readiness
    assert first.state.readiness.ready is False
    assert second.state.readiness.ready is False


def test_explicit_settings_are_respected() -> None:
    settings = Settings(environment=Environment.TEST, api=ApiSettings(v1_prefix="/custom/v1"))

    app = create_app(settings)

    assert app.state.settings is settings
    assert app.state.api_v1_prefix == "/custom/v1"


def test_routes_are_registered_once() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    paths = _registered_route_paths(app.routes)

    assert paths.count("/health/live") == 1
    assert paths.count("/health/ready") == 1


def test_version_prefix_foundation_exists() -> None:
    app = create_app(Settings(environment=Environment.TEST, api=ApiSettings(v1_prefix="/api/v1")))

    assert app.state.api_v1_prefix == "/api/v1"


def test_docs_enabled_and_disabled_behavior() -> None:
    enabled_app = create_app(
        Settings(environment=Environment.TEST, api=ApiSettings(docs_enabled=True))
    )
    disabled_app = create_app(
        Settings(environment=Environment.TEST, api=ApiSettings(docs_enabled=False))
    )

    with TestClient(enabled_app) as enabled_client:
        assert enabled_client.get("/docs").status_code == 200
        assert enabled_client.get("/openapi.json").status_code == 200

    with TestClient(disabled_app) as disabled_client:
        assert disabled_client.get("/docs").status_code == 404
        assert disabled_client.get("/openapi.json").status_code == 404


def test_app_construction_performs_no_external_connection() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    assert app.state.readiness.ready is False


def _registered_route_paths(routes: list[Any]) -> list[str]:
    paths: list[str] = []
    for route in routes:
        if isinstance(route, APIRoute):
            paths.append(route.path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            paths.extend(_registered_route_paths(list(original_router.routes)))
    return paths

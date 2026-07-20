"""API error handler tests."""

from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_api.middleware import CORRELATION_ID_HEADER
from workflowforge_application.errors import ApplicationError
from workflowforge_infrastructure.config import Environment, Settings


def test_validation_errors_use_expected_schema() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    @app.get("/_test/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    with TestClient(app) as client:
        response = client.get(
            "/_test/items/not-an-int",
            headers={CORRELATION_ID_HEADER: "validation-test"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request is invalid.",
            "correlation_id": "validation-test",
        }
    }


def test_unexpected_errors_return_sanitized_500() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    @app.get("/_test/explode")
    async def explode() -> None:
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/explode", headers={CORRELATION_ID_HEADER: "error-test"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "correlation_id": "error-test",
        }
    }
    assert "secret internals" not in response.text


def test_known_application_errors_use_sanitized_schema() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    @app.get("/_test/application-error")
    async def application_error() -> None:
        raise ApplicationError("implementation detail")

    with TestClient(app) as client:
        response = client.get(
            "/_test/application-error",
            headers={CORRELATION_ID_HEADER: "known-test"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "application_error",
            "message": "The request could not be processed.",
            "correlation_id": "known-test",
        }
    }

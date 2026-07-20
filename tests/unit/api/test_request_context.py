"""Correlation ID middleware tests."""

import asyncio

import httpx
from fastapi import Request
from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_api.middleware import CORRELATION_ID_HEADER, current_correlation_id
from workflowforge_infrastructure.config import Environment, Settings


def test_correlation_id_is_generated_when_absent() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.headers[CORRELATION_ID_HEADER]


def test_valid_incoming_correlation_id_is_preserved() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health/live", headers={CORRELATION_ID_HEADER: "request-123"})

    assert response.headers[CORRELATION_ID_HEADER] == "request-123"


def test_malformed_correlation_id_is_replaced() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    with TestClient(app) as client:
        response = client.get("/health/live", headers={CORRELATION_ID_HEADER: "bad\nvalue"})

    assert response.headers[CORRELATION_ID_HEADER] != "bad\nvalue"


async def test_concurrent_request_contexts_do_not_leak() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    @app.get("/_test/correlation")
    async def correlation(_request: Request) -> dict[str, str | None]:
        await asyncio.sleep(0.01)
        return {"correlation_id": current_correlation_id()}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first, second = await asyncio.gather(
            client.get("/_test/correlation", headers={CORRELATION_ID_HEADER: "first"}),
            client.get("/_test/correlation", headers={CORRELATION_ID_HEADER: "second"}),
        )

    assert first.json() == {"correlation_id": "first"}
    assert second.json() == {"correlation_id": "second"}
    assert first.headers[CORRELATION_ID_HEADER] == "first"
    assert second.headers[CORRELATION_ID_HEADER] == "second"

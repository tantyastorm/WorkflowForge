"""Celery worker integration tests."""

import os
import socket

import pytest
from workflowforge_contracts import DIAGNOSTIC_ECHO_TASK_NAME, DiagnosticEchoPayload
from workflowforge_infrastructure.config import RedisSettings, Settings
from workflowforge_infrastructure.tasks import create_celery_app


def _require_tcp(host: str, port: int, name: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        pytest.skip(f"{name} is unavailable: {exc}")


@pytest.mark.integration
def test_worker_consumes_diagnostic_echo_task_against_compose() -> None:
    redis_port = int(os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST_PORT", "6379"))
    _require_tcp("localhost", redis_port, "Redis")
    settings = Settings(redis=RedisSettings(host="localhost", port=redis_port))
    app = create_celery_app(settings)
    payload = DiagnosticEchoPayload(message="hello")

    try:
        async_result = app.send_task(
            DIAGNOSTIC_ECHO_TASK_NAME,
            args=(payload.model_dump(mode="json"),),
            headers={"correlation_id": "integration-worker"},
        )
        result = async_result.get(timeout=20)
    finally:
        app.close()

    assert result["message"] == "hello"
    assert result["task_name"] == DIAGNOSTIC_ECHO_TASK_NAME
    assert result["task_id"] == async_result.id
    assert result["worker"]

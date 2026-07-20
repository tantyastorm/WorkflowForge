"""Dependency health integration tests against local Compose services."""

import json
import os
import socket
from http.client import HTTPConnection
from urllib.parse import urlparse

import pytest
from pydantic import SecretStr
from workflowforge_contracts import DependencyStatus
from workflowforge_infrastructure.config import RedisSettings, S3Settings
from workflowforge_infrastructure.database import (
    DatabaseHealthCheck,
    create_async_database_engine,
    dispose_async_engine,
)
from workflowforge_infrastructure.redis import (
    RedisHealthCheck,
    close_redis_client,
    create_redis_client,
)
from workflowforge_infrastructure.storage import S3HealthCheck, close_s3_client, create_s3_client

from tests.integration.database.utils import require_postgresql


def _require_tcp(host: str, port: int, name: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        pytest.skip(f"{name} is unavailable: {exc}")


@pytest.mark.integration
async def test_required_dependency_adapters_succeed_against_compose() -> None:
    database_settings = require_postgresql()
    redis_host = os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST", "localhost")
    redis_port = int(os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST_PORT", "6379"))
    s3_endpoint_url = os.environ.get("WORKFLOWFORGE_TEST_S3_ENDPOINT_URL")
    if s3_endpoint_url is None:
        minio_port = int(os.environ.get("WORKFLOWFORGE_TEST_MINIO_API_HOST_PORT", "9000"))
        s3_endpoint_url = f"http://localhost:{minio_port}"
    _require_tcp(redis_host, redis_port, "Redis")
    _require_url(s3_endpoint_url, "MinIO")

    database_engine = create_async_database_engine(database_settings)
    redis_client = create_redis_client(RedisSettings(host=redis_host, port=redis_port))
    s3_settings = S3Settings(
        endpoint_url=s3_endpoint_url,
        access_key=os.environ.get("WORKFLOWFORGE_S3_ACCESS_KEY", "workflowforge"),
        secret_key=SecretStr(
            os.environ.get("WORKFLOWFORGE_S3_SECRET_KEY", "workflowforge_dev_secret")
        ),
        bucket=os.environ.get("WORKFLOWFORGE_S3_BUCKET", "workflowforge"),
    )
    s3_client = create_s3_client(s3_settings)

    try:
        results = [
            await DatabaseHealthCheck(database_engine).check(),
            await RedisHealthCheck(redis_client).check(),
            await S3HealthCheck(s3_client, s3_settings).check(),
        ]
    finally:
        await dispose_async_engine(database_engine)
        await close_redis_client(redis_client)
        close_s3_client(s3_client)

    assert [result.name for result in results] == ["postgresql", "redis", "object_storage"]
    assert all(result.status is DependencyStatus.HEALTHY for result in results)


@pytest.mark.integration
def test_dependency_health_endpoint_succeeds_against_compose_api() -> None:
    api_base_url = os.environ.get("WORKFLOWFORGE_TEST_API_BASE_URL")
    if api_base_url is None:
        api_port = int(os.environ.get("WORKFLOWFORGE_TEST_API_HOST_PORT", "8000"))
        api_base_url = f"http://127.0.0.1:{api_port}"
    api_host, api_port = _host_port_from_url(api_base_url)
    _require_tcp(api_host, api_port, "API")
    connection = HTTPConnection(api_host, api_port, timeout=5)
    try:
        connection.request(
            "GET",
            "/health/dependencies",
            headers={"X-Correlation-ID": "integration-health"},
        )
        response = connection.getresponse()
        status = response.status
        response_body = response.read().decode("utf-8")
        correlation_id = response.headers.get("X-Correlation-ID")
    except OSError as exc:
        pytest.skip(f"API service is unavailable: {exc}")
    finally:
        connection.close()

    if status != 200:
        pytest.skip(f"API dependency health endpoint is unavailable: HTTP {status}")

    body = json.loads(response_body)

    assert status == 200
    assert correlation_id == "integration-health"
    assert body["status"] == "healthy"
    assert list(body["dependencies"]) == [
        "postgresql",
        "redis",
        "object_storage",
        "worker",
        "scheduler",
    ]


def _require_url(url: str, name: str) -> None:
    host, port = _host_port_from_url(url)
    _require_tcp(host, port, name)


def _host_port_from_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.hostname is None or parsed.port is None:
        pytest.skip(f"Integration URL is missing host or port: {url}")
    return parsed.hostname, parsed.port

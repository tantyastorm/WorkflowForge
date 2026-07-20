"""S3-compatible object storage health adapter tests."""

from __future__ import annotations

import time
from typing import Any

from pydantic import SecretStr
from workflowforge_contracts import DependencyStatus
from workflowforge_infrastructure.config import S3Settings
from workflowforge_infrastructure.storage import S3HealthCheck, close_s3_client, create_s3_client


class FakeS3Client:
    def __init__(self, exc: Exception | None = None, *, delay_seconds: float = 0) -> None:
        self._exc = exc
        self._delay_seconds = delay_seconds
        self.head_bucket_calls: list[str] = []
        self.put_object_calls = 0
        self.closed = False

    def head_bucket(self, *, Bucket: str) -> None:
        self.head_bucket_calls.append(Bucket)
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        if self._exc is not None:
            raise self._exc

    def put_object(self, **_kwargs: Any) -> None:
        self.put_object_calls += 1

    def close(self) -> None:
        self.closed = True


def _settings(timeout_seconds: float = 1) -> S3Settings:
    return S3Settings(
        endpoint_url="http://localhost:19000",
        access_key="workflowforge",
        secret_key=SecretStr("secret"),
        bucket="workflowforge",
        timeout_seconds=timeout_seconds,
    )


async def test_s3_health_success_checks_bucket_without_writing() -> None:
    client = FakeS3Client()
    check = S3HealthCheck(client, _settings())

    result = await check.check()

    assert result.name == "object_storage"
    assert result.status is DependencyStatus.HEALTHY
    assert result.latency_ms >= 0
    assert client.head_bucket_calls == ["workflowforge"]
    assert client.put_object_calls == 0


async def test_s3_missing_bucket_is_sanitized() -> None:
    check = S3HealthCheck(FakeS3Client(exc=RuntimeError("NoSuchBucket secret")), _settings())

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "NoSuchBucket" not in result.model_dump_json()
    assert "secret" not in result.model_dump_json()


async def test_s3_access_failure_is_sanitized() -> None:
    check = S3HealthCheck(FakeS3Client(exc=RuntimeError("access-key-secret")), _settings())

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "access-key-secret" not in result.model_dump_json()


async def test_s3_timeout_is_sanitized() -> None:
    check = S3HealthCheck(FakeS3Client(delay_seconds=0.05), _settings(timeout_seconds=0.01))

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check timed out."


def test_close_s3_client_closes_client_when_supported() -> None:
    client = FakeS3Client()

    close_s3_client(client)

    assert client.closed is True


def test_create_s3_client_uses_settings_without_connecting() -> None:
    client = create_s3_client(_settings())

    assert client.meta.endpoint_url == "http://localhost:19000"
    close_s3_client(client)

"""S3-compatible object storage health adapter tests."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr
from workflowforge_application.documents import PromoteObjectRequest
from workflowforge_contracts import DependencyStatus
from workflowforge_domain.documents import ContentHash, StorageObjectKey
from workflowforge_infrastructure.config import S3Settings
from workflowforge_infrastructure.storage import (
    ObjectStorageError,
    S3HealthCheck,
    S3ObjectStorage,
    close_s3_client,
    create_s3_client,
)


class FakeS3Client:
    def __init__(self, exc: Exception | None = None, *, delay_seconds: float = 0) -> None:
        self._exc = exc
        self._delay_seconds = delay_seconds
        self.head_bucket_calls: list[str] = []
        self.head_object_calls: list[str] = []
        self.copy_object_calls: list[dict[str, Any]] = []
        self.delete_object_calls: list[str] = []
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

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.head_object_calls.append(f"{Bucket}/{Key}")
        if self._exc is not None:
            raise self._exc
        return {"ContentLength": 123, "ETag": '"etag"', "ContentType": "application/pdf"}

    def copy_object(self, **kwargs: Any) -> None:
        self.copy_object_calls.append(kwargs)
        if self._exc is not None:
            raise self._exc

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.delete_object_calls.append(f"{Bucket}/{Key}")

    def generate_presigned_url(self, *_args: Any, **_kwargs: Any) -> str:
        return "http://localhost/download"

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


async def test_s3_object_storage_head_object_maps_metadata() -> None:
    client = FakeS3Client()
    storage = S3ObjectStorage(client, _settings())
    key = _document_key()

    metadata = await storage.head_object(key)

    assert metadata is not None
    assert metadata.key == key
    assert metadata.byte_size == 123
    assert client.head_object_calls == [f"workflowforge/{key.value}"]


async def test_s3_object_storage_head_object_maps_missing_to_none() -> None:
    storage = S3ObjectStorage(FakeS3Client(exc=RuntimeError("NoSuchKey")), _settings())

    assert await storage.head_object(_document_key()) is None


async def test_s3_object_storage_promotion_copies_then_deletes() -> None:
    client = FakeS3Client()
    storage = S3ObjectStorage(client, _settings())
    temp_key = StorageObjectKey.for_temporary_upload(
        organization_id=_organization_id(),
        upload_id=_upload_id(),
    )
    final_key = _document_key()

    metadata = await storage.promote_temp_object(
        PromoteObjectRequest(source_key=temp_key, destination_key=final_key)
    )

    assert metadata.key == final_key
    assert client.copy_object_calls[0]["Key"] == final_key.value
    assert client.delete_object_calls == [f"workflowforge/{temp_key.value}"]


async def test_s3_object_storage_rejects_invalid_promotion_keys() -> None:
    storage = S3ObjectStorage(FakeS3Client(), _settings())

    with pytest.raises(ObjectStorageError, match="Final object key"):
        await storage.promote_temp_object(
            PromoteObjectRequest(
                source_key=StorageObjectKey.for_temporary_upload(
                    organization_id=_organization_id(),
                    upload_id=_upload_id(),
                ),
                destination_key=StorageObjectKey.for_temporary_upload(
                    organization_id=_organization_id(),
                    upload_id=_upload_id(),
                ),
            )
        )


async def test_s3_object_storage_creates_bounded_download_url() -> None:
    storage = S3ObjectStorage(FakeS3Client(), _settings())

    result = await storage.create_download_url(
        key=_document_key(),
        expires_in_seconds=60,
        now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert result.url == "http://localhost/download"
    assert result.expires_at.isoformat() == "2026-01-02T03:05:05+00:00"


def _organization_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _upload_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _document_key() -> StorageObjectKey:
    return StorageObjectKey.for_document_content(
        organization_id=_organization_id(),
        content_hash=ContentHash("a" * 64),
    )

"""S3-compatible client factory."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

from workflowforge_application.documents import (
    DownloadUrl,
    PromoteObjectRequest,
    PutTempObjectRequest,
    StoredObjectMetadata,
)
from workflowforge_domain.documents import StorageObjectKey

from workflowforge_infrastructure.config import S3Settings


def create_s3_client(settings: S3Settings) -> Any:
    """Create a boto3 S3-compatible client without performing network I/O."""

    boto3 = importlib.import_module("boto3")
    botocore_config = importlib.import_module("botocore.config")
    config = botocore_config.Config(
        connect_timeout=settings.timeout_seconds,
        read_timeout=settings.timeout_seconds,
        retries={"max_attempts": 1},
        s3={"addressing_style": "path"},
    )
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key.get_secret_value(),
        region_name=settings.region,
        use_ssl=settings.use_ssl,
        config=config,
    )


def close_s3_client(client: Any) -> None:
    """Close a boto3 client when supported."""

    close = getattr(client, "close", None)
    if callable(close):
        close()


class ObjectStorageError(RuntimeError):
    """Base class for object-storage adapter failures."""


class ObjectPromotionError(ObjectStorageError):
    """Raised when temporary-to-final promotion fails."""


class S3ObjectStorage:
    """S3-compatible implementation of the application object-storage port."""

    def __init__(self, client: Any, settings: S3Settings) -> None:
        self._client = client
        self._bucket = settings.bucket

    async def put_temp_stream(self, request: PutTempObjectRequest) -> StoredObjectMetadata:
        """Write a temporary object."""

        _require_prefix(request.key, "tmp/")
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=request.key.value,
                Body=request.body,
                ContentType=request.media_type,
            )
        except Exception as exc:
            msg = "Temporary object write failed."
            raise ObjectStorageError(msg) from exc
        return await self.head_object(request.key) or StoredObjectMetadata(
            key=request.key,
            byte_size=0,
            media_type=request.media_type,
        )

    async def promote_temp_object(self, request: PromoteObjectRequest) -> StoredObjectMetadata:
        """Copy a temporary object to a final key, then delete the temporary key.

        S3-compatible storage has no atomic rename. Step 3 orchestration must
        tolerate copy success followed by delete failure as a retryable cleanup
        concern.
        """

        _require_prefix(request.source_key, "tmp/")
        _require_final_key(request.destination_key)
        try:
            self._client.copy_object(
                Bucket=self._bucket,
                Key=request.destination_key.value,
                CopySource={"Bucket": self._bucket, "Key": request.source_key.value},
                **({"ContentType": request.media_type} if request.media_type is not None else {}),
            )
            self._client.delete_object(Bucket=self._bucket, Key=request.source_key.value)
        except Exception as exc:
            msg = "Object promotion failed."
            raise ObjectPromotionError(msg) from exc
        metadata = await self.head_object(request.destination_key)
        if metadata is None:
            msg = "Promoted object was not found."
            raise ObjectPromotionError(msg)
        return metadata

    async def head_object(self, key: StorageObjectKey) -> StoredObjectMetadata | None:
        """Return object metadata when the key exists."""

        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key.value)
        except Exception as exc:
            if _looks_missing(exc):
                return None
            msg = "Object metadata lookup failed."
            raise ObjectStorageError(msg) from exc
        return StoredObjectMetadata(
            key=key,
            byte_size=int(response.get("ContentLength", 0)),
            etag=response.get("ETag"),
            media_type=response.get("ContentType"),
        )

    async def delete_object(self, key: StorageObjectKey) -> None:
        """Delete an object key idempotently."""

        try:
            self._client.delete_object(Bucket=self._bucket, Key=key.value)
        except Exception as exc:
            msg = "Object deletion failed."
            raise ObjectStorageError(msg) from exc

    async def create_download_url(
        self,
        *,
        key: StorageObjectKey,
        expires_in_seconds: int,
        now: datetime,
    ) -> DownloadUrl:
        """Create a bounded download URL without exposing storage credentials."""

        if expires_in_seconds <= 0 or expires_in_seconds > 3600:
            msg = "Download URL expiry must be between 1 and 3600 seconds."
            raise ObjectStorageError(msg)
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key.value},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            msg = "Download URL creation failed."
            raise ObjectStorageError(msg) from exc
        timestamp = (
            now if now.tzinfo is not None and now.utcoffset() is not None else datetime.now(UTC)
        )
        return DownloadUrl(
            url=url, expires_at=timestamp.astimezone(UTC) + timedelta(seconds=expires_in_seconds)
        )


def _require_prefix(key: StorageObjectKey, prefix: str) -> None:
    if not key.value.startswith(prefix):
        msg = f"Object key must use the {prefix!r} prefix."
        raise ObjectStorageError(msg)


def _require_final_key(key: StorageObjectKey) -> None:
    if not (key.value.startswith("documents/") or key.value.startswith("artifacts/")):
        msg = "Final object key must be a document or artifact key."
        raise ObjectStorageError(msg)


def _looks_missing(exc: Exception) -> bool:
    text = str(exc)
    return "404" in text or "NoSuchKey" in text or "NotFound" in text

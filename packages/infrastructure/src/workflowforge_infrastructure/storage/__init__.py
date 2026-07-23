"""Object storage infrastructure adapters."""

from workflowforge_infrastructure.storage.health import S3HealthCheck
from workflowforge_infrastructure.storage.s3 import (
    ObjectPromotionError,
    ObjectStorageError,
    S3ObjectStorage,
    close_s3_client,
    create_s3_client,
)

__all__ = [
    "ObjectPromotionError",
    "ObjectStorageError",
    "S3HealthCheck",
    "S3ObjectStorage",
    "close_s3_client",
    "create_s3_client",
]

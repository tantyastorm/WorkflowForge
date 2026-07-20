"""S3-compatible client factory."""

from __future__ import annotations

import importlib
from typing import Any

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

"""Object storage dependency health check."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from workflowforge_contracts import DependencyHealthResult, DependencyStatus

from workflowforge_infrastructure.config import S3Settings

_SANITIZED_FAILURE_DETAIL = "Dependency check failed."
_SANITIZED_TIMEOUT_DETAIL = "Dependency check timed out."


class S3HealthCheck:
    """Check S3-compatible object storage bucket reachability."""

    name = "object_storage"

    def __init__(self, client: Any, settings: S3Settings) -> None:
        self._client = client
        self._bucket = settings.bucket
        self._timeout_seconds = settings.timeout_seconds

    async def check(self) -> DependencyHealthResult:
        """Return object storage health using a bucket metadata check."""

        started_at = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except TimeoutError:
            return DependencyHealthResult(
                name=self.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=_latency_ms(started_at),
                detail=_SANITIZED_TIMEOUT_DETAIL,
            )
        except Exception:
            return DependencyHealthResult(
                name=self.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=_latency_ms(started_at),
                detail=_SANITIZED_FAILURE_DETAIL,
            )

        return DependencyHealthResult(
            name=self.name,
            status=DependencyStatus.HEALTHY,
            latency_ms=_latency_ms(started_at),
        )


def _latency_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)

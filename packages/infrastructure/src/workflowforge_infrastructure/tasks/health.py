"""Worker and scheduler dependency health checks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from workflowforge_contracts import DependencyHealthResult, DependencyStatus

from workflowforge_infrastructure.config import SchedulerSettings

_SANITIZED_FAILURE_DETAIL = "Dependency check failed."
_SANITIZED_TIMEOUT_DETAIL = "Dependency check timed out."


class WorkerHealthCheck:
    """Check whether at least one Celery worker answers inspect ping."""

    name = "worker"

    def __init__(self, app: Any, *, timeout_seconds: float) -> None:
        self._app = app
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealthResult:
        """Return worker health using a real Celery inspect ping."""

        started_at = perf_counter()
        try:
            replies = await asyncio.wait_for(
                asyncio.to_thread(self._ping_workers),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            return _unhealthy(self.name, started_at, _SANITIZED_TIMEOUT_DETAIL)
        except Exception:
            return _unhealthy(self.name, started_at, _SANITIZED_FAILURE_DETAIL)

        worker_count = len(replies)
        if worker_count == 0:
            return _unhealthy(self.name, started_at, "No workers responded.")

        return DependencyHealthResult(
            name=self.name,
            status=DependencyStatus.HEALTHY,
            latency_ms=_latency_ms(started_at),
            detail=f"{worker_count} worker responded.",
        )

    def _ping_workers(self) -> dict[str, Any]:
        inspect_timeout = max(0.5, self._timeout_seconds - 1.0)
        inspector = self._app.control.inspect(timeout=inspect_timeout)
        replies = inspector.ping()
        return replies if isinstance(replies, dict) else {}


class SchedulerHealthCheck:
    """Check scheduler visibility through its Redis heartbeat."""

    name = "scheduler"

    def __init__(
        self,
        client: Redis,
        settings: SchedulerSettings,
        *,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._settings = settings
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealthResult:
        """Return scheduler health from the heartbeat timestamp."""

        started_at = perf_counter()
        try:
            raw_heartbeat = await asyncio.wait_for(
                self._client.get(self._settings.heartbeat_key),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, RedisTimeoutError):
            return _unhealthy(self.name, started_at, _SANITIZED_TIMEOUT_DETAIL)
        except RedisError:
            return _unhealthy(self.name, started_at, _SANITIZED_FAILURE_DETAIL)

        if raw_heartbeat is None:
            return _unhealthy(self.name, started_at, "Scheduler heartbeat is missing.")
        if not isinstance(raw_heartbeat, str):
            return _unhealthy(self.name, started_at, "Scheduler heartbeat is malformed.")

        try:
            observed_at = datetime.fromisoformat(raw_heartbeat)
        except ValueError:
            return _unhealthy(self.name, started_at, "Scheduler heartbeat is malformed.")

        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        age_seconds = (datetime.now(UTC) - observed_at.astimezone(UTC)).total_seconds()
        if age_seconds > self._settings.heartbeat_ttl_seconds:
            return _unhealthy(self.name, started_at, "Scheduler heartbeat is stale.")

        return DependencyHealthResult(
            name=self.name,
            status=DependencyStatus.HEALTHY,
            latency_ms=_latency_ms(started_at),
            detail=None,
        )


def _unhealthy(name: str, started_at: float, detail: str) -> DependencyHealthResult:
    return DependencyHealthResult(
        name=name,
        status=DependencyStatus.UNHEALTHY,
        latency_ms=_latency_ms(started_at),
        detail=detail,
    )


def _latency_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)

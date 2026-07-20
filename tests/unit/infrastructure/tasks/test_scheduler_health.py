"""Scheduler heartbeat health tests."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from redis.exceptions import ConnectionError, TimeoutError
from workflowforge_contracts import DependencyStatus
from workflowforge_infrastructure.config import SchedulerSettings
from workflowforge_infrastructure.tasks import SchedulerHealthCheck


class FakeRedisClient:
    def __init__(self, value: object = None, exc: Exception | None = None) -> None:
        self._value = value
        self._exc = exc

    async def get(self, key: str) -> object:
        if self._exc is not None:
            raise self._exc
        assert key == "workflowforge:diagnostics:scheduler:last_seen"
        return self._value


def _settings() -> SchedulerSettings:
    return SchedulerSettings(heartbeat_interval_seconds=5, heartbeat_ttl_seconds=15)


async def test_scheduler_health_is_healthy_with_recent_heartbeat() -> None:
    client = FakeRedisClient(datetime.now(UTC).isoformat())

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.name == "scheduler"
    assert result.status is DependencyStatus.HEALTHY
    assert result.detail is None


async def test_scheduler_health_reports_missing_heartbeat() -> None:
    client = FakeRedisClient(None)

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Scheduler heartbeat is missing."


async def test_scheduler_health_reports_stale_heartbeat() -> None:
    client = FakeRedisClient((datetime.now(UTC) - timedelta(seconds=20)).isoformat())

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Scheduler heartbeat is stale."


async def test_scheduler_health_reports_malformed_heartbeat() -> None:
    client = FakeRedisClient("not-a-date")

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Scheduler heartbeat is malformed."


async def test_scheduler_health_sanitizes_redis_timeout() -> None:
    client = FakeRedisClient(exc=TimeoutError("redis://secret"))

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check timed out."
    assert "redis://secret" not in result.model_dump_json()


async def test_scheduler_health_sanitizes_redis_failure() -> None:
    client = FakeRedisClient(exc=ConnectionError("redis://secret"))

    result = await SchedulerHealthCheck(cast("Any", client), _settings(), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "redis://secret" not in result.model_dump_json()

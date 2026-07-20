"""Redis health adapter tests."""

from typing import Any, cast

from pydantic import SecretStr
from redis.exceptions import ConnectionError, TimeoutError
from workflowforge_contracts import DependencyStatus
from workflowforge_infrastructure.config import RedisSettings
from workflowforge_infrastructure.redis import (
    RedisHealthCheck,
    close_redis_client,
    create_redis_client,
)


class FakeRedisClient:
    def __init__(self, result: object = True, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.closed = False

    async def ping(self) -> object:
        if self._exc is not None:
            raise self._exc
        return self._result

    async def aclose(self) -> None:
        self.closed = True


async def test_redis_health_ping_success() -> None:
    check = RedisHealthCheck(cast("Any", FakeRedisClient()))

    result = await check.check()

    assert result.name == "redis"
    assert result.status is DependencyStatus.HEALTHY
    assert result.latency_ms >= 0
    assert result.detail is None


async def test_redis_health_timeout_is_sanitized() -> None:
    check = RedisHealthCheck(cast("Any", FakeRedisClient(exc=TimeoutError("secret"))))

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check timed out."
    assert "secret" not in result.model_dump_json()


async def test_redis_health_connection_failure_is_sanitized() -> None:
    check = RedisHealthCheck(cast("Any", FakeRedisClient(exc=ConnectionError("redis://secret"))))

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "redis://secret" not in result.model_dump_json()


async def test_redis_health_unexpected_ping_value_is_unhealthy() -> None:
    check = RedisHealthCheck(cast("Any", FakeRedisClient(result=False)))

    result = await check.check()

    assert result.status is DependencyStatus.UNHEALTHY


async def test_close_redis_client_closes_client() -> None:
    client = FakeRedisClient()

    await close_redis_client(cast("Any", client))

    assert client.closed is True


def test_create_redis_client_uses_settings_without_connecting() -> None:
    client = create_redis_client(
        RedisSettings(
            host="localhost",
            port=16379,
            db=1,
            password=SecretStr("secret"),
            ssl=False,
            socket_timeout_seconds=1,
        )
    )

    assert client.connection_pool.connection_kwargs["host"] == "localhost"
    assert client.connection_pool.connection_kwargs["port"] == 16379
    assert client.connection_pool.connection_kwargs["password"] == "secret"

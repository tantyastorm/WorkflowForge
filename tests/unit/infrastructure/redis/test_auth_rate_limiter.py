"""Redis authentication rate limiter tests."""

from __future__ import annotations

from typing import Any, cast

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from workflowforge_application.security.errors import RateLimitUnavailableError
from workflowforge_infrastructure.config import RateLimitFailurePolicy, RateLimitSettings
from workflowforge_infrastructure.security import RedisAuthenticationRateLimiter


@pytest.mark.asyncio
async def test_login_failures_are_limited_by_identifier_and_clear_on_success() -> None:
    redis = FakeRedis()
    limiter = RedisAuthenticationRateLimiter(
        redis,
        RateLimitSettings(
            login_identifier_threshold=2,
            login_client_threshold=10,
            login_window_seconds=60,
        ),
    )

    first = await limiter.check_login_allowed(
        normalized_identifier="ada@example.com",
        client_key="198.51.100.10",
    )
    second = await limiter.record_login_failure(
        normalized_identifier="ada@example.com",
        client_key="198.51.100.10",
    )
    third = await limiter.record_login_failure(
        normalized_identifier="ada@example.com",
        client_key="198.51.100.10",
    )

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds == 60
    assert redis.eval_calls == 4
    assert not any("ada@example.com" in key for key in redis.values)
    assert not any("198.51.100.10" in key for key in redis.values)

    await limiter.record_login_success(
        normalized_identifier="ada@example.com",
        client_key="198.51.100.10",
    )

    assert redis.values == {}


@pytest.mark.asyncio
async def test_refresh_failures_are_limited_and_retry_after_uses_ttl() -> None:
    redis = FakeRedis()
    limiter = RedisAuthenticationRateLimiter(
        redis,
        RateLimitSettings(refresh_client_threshold=1, refresh_window_seconds=30),
    )

    decision = await limiter.record_refresh_failure(client_key="client one")

    assert decision.allowed is False
    assert decision.retry_after_seconds == 30
    assert len(redis.values) == 1
    assert "client one" not in next(iter(redis.values.keys()))

    await limiter.record_refresh_success(client_key="client one")

    assert redis.values == {}


@pytest.mark.asyncio
async def test_fail_open_allows_auth_when_redis_is_unavailable() -> None:
    limiter = RedisAuthenticationRateLimiter(
        FailingRedis(),
        RateLimitSettings(failure_policy=RateLimitFailurePolicy.OPEN),
    )

    decision = await limiter.record_refresh_failure(client_key="client")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_fail_closed_rejects_auth_when_redis_is_unavailable() -> None:
    limiter = RedisAuthenticationRateLimiter(
        FailingRedis(),
        RateLimitSettings(failure_policy=RateLimitFailurePolicy.CLOSED),
    )

    with pytest.raises(RateLimitUnavailableError):
        await limiter.record_refresh_failure(client_key="client")


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.eval_calls = 0

    async def eval(self, _script: str, numkeys: int, *keys_and_args: object) -> list[int]:
        assert numkeys == 1
        key = str(keys_and_args[0])
        window_seconds = int(cast(str | int, keys_and_args[1]))
        self.eval_calls += 1
        self.values[key] = self.values.get(key, 0) + 1
        if self.values[key] == 1:
            self.ttls[key] = window_seconds
        return [self.values[key], self.ttls[key]]

    async def get(self, key: str) -> int | None:
        return self.values.get(key)

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)


class FailingRedis:
    async def eval(self, _script: str, _numkeys: int, *_keys_and_args: object) -> Any:
        raise RedisConnectionError("down")

    async def get(self, _key: str) -> Any:
        raise RedisConnectionError("down")

    async def ttl(self, _key: str) -> int:
        raise RedisConnectionError("down")

    async def delete(self, *_keys: str) -> Any:
        raise RedisError("down")

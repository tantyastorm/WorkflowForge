"""Redis authentication rate limiter integration tests."""

from __future__ import annotations

import os
import socket

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from workflowforge_infrastructure.config import RateLimitSettings, RedisSettings
from workflowforge_infrastructure.redis import close_redis_client, create_redis_client
from workflowforge_infrastructure.security import RedisAuthenticationRateLimiter


@pytest.mark.integration
async def test_redis_rate_limiter_lua_ttl_threshold_and_key_privacy() -> None:
    client = await _require_redis()
    try:
        await _clear_rate_limit_keys(client)
        limiter = RedisAuthenticationRateLimiter(
            client,
            RateLimitSettings(
                login_identifier_threshold=2,
                login_client_threshold=10,
                login_window_seconds=60,
                refresh_client_threshold=1,
                refresh_window_seconds=30,
            ),
        )

        first = await limiter.record_login_failure(
            normalized_identifier="ada@example.com",
            client_key="198.51.100.10/raw value",
        )
        second = await limiter.record_login_failure(
            normalized_identifier="ada@example.com",
            client_key="198.51.100.10/raw value",
        )
        refresh = await limiter.record_refresh_failure(client_key="198.51.100.10/raw value")

        keys = sorted([str(key) async for key in client.scan_iter("workflowforge:ratelimit:*")])
        ttls = {key: await client.ttl(key) for key in keys}

        assert first.allowed is True
        assert second.allowed is False
        assert second.retry_after_seconds == 60
        assert refresh.allowed is False
        assert refresh.retry_after_seconds == 30
        assert any(":login:identifier:" in key for key in keys)
        assert any(":login:client:" in key for key in keys)
        assert any(":refresh:client:" in key for key in keys)
        assert all(ttl > 0 for ttl in ttls.values())
        assert not any("ada@example.com" in key for key in keys)
        assert not any("198.51.100.10" in key for key in keys)
        assert not any("raw value" in key for key in keys)

        await limiter.record_login_success(
            normalized_identifier="ada@example.com",
            client_key="198.51.100.10/raw value",
        )
        remaining = [str(key) async for key in client.scan_iter("workflowforge:ratelimit:*")]
        assert all(":login:" not in key for key in remaining)
    finally:
        await _clear_rate_limit_keys(client)
        await close_redis_client(client)


async def _require_redis() -> Redis:
    host = os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST", "localhost")
    port = int(os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST_PORT", "6379"))
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        pytest.skip(f"Redis integration service is unavailable: {exc}")

    client = create_redis_client(RedisSettings(host=host, port=port))
    try:
        await client.ping()
    except RedisError as exc:
        await close_redis_client(client)
        pytest.skip(f"Redis integration service is unavailable: {exc}")
    return client


async def _clear_rate_limit_keys(client: Redis) -> None:
    keys = [str(key) async for key in client.scan_iter("workflowforge:ratelimit:*")]
    if keys:
        await client.delete(*keys)

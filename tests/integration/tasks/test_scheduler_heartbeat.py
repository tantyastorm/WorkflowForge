"""Scheduler heartbeat integration tests."""

import asyncio
import os
import socket
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from workflowforge_infrastructure.config import RedisSettings, SchedulerSettings
from workflowforge_infrastructure.redis import close_redis_client, create_redis_client


def _require_tcp(host: str, port: int, name: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError as exc:
        pytest.skip(f"{name} is unavailable: {exc}")


@pytest.mark.integration
async def test_scheduler_publishes_recent_heartbeat_against_compose() -> None:
    redis_host = os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST", "localhost")
    redis_port = int(os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST_PORT", "6379"))
    _require_tcp(redis_host, redis_port, "Redis")
    settings = SchedulerSettings()
    client = create_redis_client(RedisSettings(host=redis_host, port=redis_port))

    try:
        heartbeat = await _wait_for_heartbeat(client, settings)
    finally:
        await close_redis_client(client)

    observed_at = datetime.fromisoformat(heartbeat).astimezone(UTC)
    assert (datetime.now(UTC) - observed_at).total_seconds() <= settings.heartbeat_ttl_seconds


async def _wait_for_heartbeat(client: Redis, settings: SchedulerSettings) -> str:
    deadline = asyncio.get_running_loop().time() + settings.heartbeat_interval_seconds + 20
    while asyncio.get_running_loop().time() < deadline:
        heartbeat = await client.get(settings.heartbeat_key)
        if isinstance(heartbeat, str):
            return heartbeat
        await asyncio.sleep(1)
    pytest.fail("Scheduler heartbeat was not observed before the bounded deadline.")

"""Redis client factory."""

from redis.asyncio import Redis

from workflowforge_infrastructure.config import RedisSettings


def create_redis_client(settings: RedisSettings) -> Redis:
    """Create an async Redis client without opening a connection at import time."""

    return Redis(
        host=settings.host,
        port=settings.port,
        db=settings.db,
        password=(settings.password.get_secret_value() if settings.password is not None else None),
        ssl=settings.ssl,
        socket_timeout=settings.socket_timeout_seconds,
        socket_connect_timeout=settings.socket_timeout_seconds,
        decode_responses=True,
    )


async def close_redis_client(client: Redis) -> None:
    """Close an async Redis client."""

    await client.aclose()

"""Redis dependency health check."""

from time import perf_counter

from redis.asyncio import Redis
from redis.exceptions import RedisError, TimeoutError
from workflowforge_contracts import DependencyHealthResult, DependencyStatus

_SANITIZED_FAILURE_DETAIL = "Dependency check failed."
_SANITIZED_TIMEOUT_DETAIL = "Dependency check timed out."


class RedisHealthCheck:
    """Check Redis availability with PING."""

    name = "redis"

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def check(self) -> DependencyHealthResult:
        """Return Redis health using a real PING."""

        started_at = perf_counter()
        try:
            pong = await self._client.ping()
        except TimeoutError:
            return DependencyHealthResult(
                name=self.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=_latency_ms(started_at),
                detail=_SANITIZED_TIMEOUT_DETAIL,
            )
        except RedisError:
            return DependencyHealthResult(
                name=self.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=_latency_ms(started_at),
                detail=_SANITIZED_FAILURE_DETAIL,
            )

        if pong is not True:
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

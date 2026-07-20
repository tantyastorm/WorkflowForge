"""Database health checks."""

import asyncio
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from workflowforge_contracts import (
    DependencyHealth,
    DependencyHealthResult,
    DependencyState,
    DependencyStatus,
)

from workflowforge_infrastructure.database.errors import DatabaseUnavailableError

_SANITIZED_FAILURE_DETAIL = "Dependency check failed."


async def check_database_health(
    engine: AsyncEngine,
    *,
    timeout_seconds: float = 5.0,
) -> DependencyHealth:
    """Check database availability with a lightweight query."""

    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (TimeoutError, SQLAlchemyError) as exc:
        raise DatabaseUnavailableError("Database health check failed.") from exc

    return DependencyHealth(name="postgresql", state=DependencyState.AVAILABLE)


class DatabaseHealthCheck:
    """Application health-check adapter for PostgreSQL."""

    name = "postgresql"

    def __init__(self, engine: AsyncEngine, *, timeout_seconds: float = 3.0) -> None:
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealthResult:
        """Check PostgreSQL health with latency measurement."""

        started_at = perf_counter()
        try:
            await check_database_health(self._engine, timeout_seconds=self._timeout_seconds)
        except DatabaseUnavailableError:
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

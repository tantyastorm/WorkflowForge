"""Database health checks."""

import asyncio

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from workflowforge_contracts import DependencyHealth, DependencyState

from workflowforge_infrastructure.database.errors import DatabaseUnavailableError


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

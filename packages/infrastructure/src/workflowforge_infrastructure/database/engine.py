"""Database engine factories."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from workflowforge_infrastructure.config import DatabaseSettings


def create_async_database_engine(database: DatabaseSettings) -> AsyncEngine:
    """Create an async SQLAlchemy engine for application runtime."""

    return create_async_engine(
        database.async_sqlalchemy_url(),
        connect_args={"timeout": database.pool_timeout_seconds},
        echo=database.echo,
        pool_size=database.pool_size,
        max_overflow=database.max_overflow,
        pool_timeout=database.pool_timeout_seconds,
        pool_pre_ping=True,
    )


def create_sync_migration_engine(database: DatabaseSettings) -> Engine:
    """Create a synchronous SQLAlchemy engine for migration execution."""

    return create_engine(
        database.sync_sqlalchemy_url(),
        connect_args={"connect_timeout": int(database.pool_timeout_seconds)},
        echo=database.echo,
        pool_pre_ping=True,
    )


async def dispose_async_engine(engine: AsyncEngine) -> None:
    """Dispose an async engine."""

    await engine.dispose()

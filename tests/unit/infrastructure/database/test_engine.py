"""Database engine factory tests."""

from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from workflowforge_infrastructure.config import DatabaseSettings
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_sync_migration_engine,
    dispose_async_engine,
)
from workflowforge_infrastructure.database import engine as engine_module


def test_database_engine_module_has_no_global_engine() -> None:
    assert not isinstance(getattr(engine_module, "engine", None), (AsyncEngine, Engine))


def test_create_async_engine_uses_database_settings() -> None:
    settings = DatabaseSettings(
        host="db.example.test",
        port=15432,
        name="workflowforge_test",
        user="tester",
        password=SecretStr("testing"),
        pool_size=2,
        max_overflow=3,
        pool_timeout_seconds=4,
    )

    engine = create_async_database_engine(settings)

    try:
        assert isinstance(engine, AsyncEngine)
        assert engine.url.drivername == "postgresql+asyncpg"
        assert engine.url.host == "db.example.test"
        assert engine.url.port == 15432
        assert engine.echo is False
    finally:
        engine.sync_engine.dispose()


def test_create_sync_migration_engine_uses_psycopg_driver() -> None:
    settings = DatabaseSettings()

    engine = create_sync_migration_engine(settings)

    try:
        assert isinstance(engine, Engine)
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


async def test_dispose_async_engine() -> None:
    engine = create_async_database_engine(DatabaseSettings())

    await dispose_async_engine(engine)

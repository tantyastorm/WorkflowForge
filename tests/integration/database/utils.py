"""Database integration test helpers."""

import socket

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from workflowforge_infrastructure.config import DatabaseSettings, Settings
from workflowforge_infrastructure.database import create_sync_migration_engine


def integration_database_settings() -> DatabaseSettings:
    """Return database settings from WORKFLOWFORGE_DATABASE_* environment variables."""

    return Settings().database


def require_postgresql() -> DatabaseSettings:
    """Return database settings or skip when PostgreSQL is unavailable."""

    settings = integration_database_settings()
    try:
        with socket.create_connection((settings.host, settings.port), timeout=2):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")

    engine = create_sync_migration_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
    finally:
        engine.dispose()

    return settings

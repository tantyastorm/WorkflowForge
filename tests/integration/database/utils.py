"""Database integration test helpers."""

import os
import socket

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from workflowforge_infrastructure.config import DatabaseSettings, Settings
from workflowforge_infrastructure.database import create_sync_migration_engine


def integration_database_settings() -> DatabaseSettings:
    """Return host-side database settings for integration tests."""

    default_settings = Settings().database
    return DatabaseSettings(
        host=os.environ.get("WORKFLOWFORGE_TEST_DATABASE_HOST", default_settings.host),
        port=int(
            os.environ.get("WORKFLOWFORGE_TEST_DATABASE_HOST_PORT", str(default_settings.port))
        ),
        name=os.environ.get("WORKFLOWFORGE_TEST_DATABASE_NAME", default_settings.name),
        user=os.environ.get("WORKFLOWFORGE_TEST_DATABASE_USER", default_settings.user),
        password=SecretStr(
            os.environ.get(
                "WORKFLOWFORGE_TEST_DATABASE_PASSWORD",
                default_settings.password.get_secret_value(),
            )
        ),
        echo=default_settings.echo,
        pool_size=default_settings.pool_size,
        max_overflow=default_settings.max_overflow,
        pool_timeout_seconds=default_settings.pool_timeout_seconds,
    )


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

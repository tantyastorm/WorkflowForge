"""Alembic migration integration tests."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from workflowforge_infrastructure.config import DatabaseSettings
from workflowforge_infrastructure.database import create_sync_migration_engine

from tests.integration.database.utils import require_postgresql


@pytest.mark.integration
def test_baseline_migration_upgrade_downgrade_and_reupgrade() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.current(alembic_config)

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        assert inspector.get_table_names() == ["alembic_version"]
        with engine.connect() as connection:
            version_rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            assert version_rows.scalar_one() == "0001_baseline"
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


@pytest.mark.integration
def test_metadata_has_no_business_tables_after_baseline() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        table_names = inspect(engine).get_table_names()
    finally:
        engine.dispose()

    assert table_names == ["alembic_version"]


def _alembic_config(settings: DatabaseSettings) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = settings
    return config

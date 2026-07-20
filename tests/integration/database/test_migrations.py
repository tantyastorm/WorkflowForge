"""Alembic migration integration tests."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from workflowforge_infrastructure.config import DatabaseSettings
from workflowforge_infrastructure.database import create_sync_migration_engine

from tests.integration.database.utils import require_postgresql


@pytest.mark.integration
def test_migrations_upgrade_from_empty_downgrade_and_reupgrade() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.current(alembic_config)

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        assert inspector.get_table_names() == ["alembic_version", "documents"]
        with engine.connect() as connection:
            version_rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            assert version_rows.scalar_one() == "0002_create_documents"
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


@pytest.mark.integration
def test_documents_table_has_expected_columns_and_constraints_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("documents")}
        constraints = {
            constraint["name"] for constraint in inspector.get_check_constraints("documents")
        }
        unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("documents")
        }
        indexes = {index["name"] for index in inspector.get_indexes("documents")}
    finally:
        engine.dispose()

    assert set(columns) == {
        "id",
        "original_filename",
        "media_type",
        "byte_size",
        "content_hash",
        "storage_object_key",
        "status",
        "created_at",
        "updated_at",
    }
    assert columns["byte_size"]["nullable"] is False
    assert "ck_documents_byte_size_non_negative" in constraints
    assert "ck_documents_status_valid" in constraints
    assert "uq_documents_content_hash" in unique_constraints
    assert "uq_documents_storage_object_key" in unique_constraints
    assert "ix_documents_content_hash" in indexes


@pytest.mark.integration
def test_downgrade_to_baseline_removes_documents_table() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "0001_baseline")

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

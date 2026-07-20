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
        table_names = set(inspector.get_table_names())
        assert table_names == {
            "alembic_version",
            "documents",
            "memberships",
            "organizations",
            "users",
        }
        with engine.connect() as connection:
            version_rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            assert version_rows.scalar_one() == "0004_memberships"
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
def test_identity_tables_have_expected_columns_constraints_and_indexes_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        user_columns = {column["name"]: column for column in inspector.get_columns("users")}
        organization_columns = {
            column["name"]: column for column in inspector.get_columns("organizations")
        }
        membership_columns = {
            column["name"]: column for column in inspector.get_columns("memberships")
        }
        user_unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("users")
        }
        organization_unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("organizations")
        }
        membership_unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("memberships")
        }
        membership_check_constraints = {
            constraint["name"] for constraint in inspector.get_check_constraints("memberships")
        }
        membership_indexes = {index["name"] for index in inspector.get_indexes("memberships")}
        user_indexes = {index["name"] for index in inspector.get_indexes("users")}
        organization_indexes = {index["name"] for index in inspector.get_indexes("organizations")}
    finally:
        engine.dispose()

    assert set(user_columns) == {
        "id",
        "email",
        "normalized_email",
        "display_name",
        "is_active",
        "created_at",
        "updated_at",
        "disabled_at",
    }
    assert set(organization_columns) == {
        "id",
        "name",
        "slug",
        "is_active",
        "created_at",
        "updated_at",
        "deactivated_at",
    }
    assert set(membership_columns) == {
        "id",
        "user_id",
        "organization_id",
        "role",
        "status",
        "invited_at",
        "joined_at",
        "suspended_at",
        "removed_at",
        "created_at",
        "updated_at",
    }
    assert "uq_users_normalized_email" in user_unique_constraints
    assert "uq_organizations_slug" in organization_unique_constraints
    assert "uq_memberships_organization_user" in membership_unique_constraints
    assert "ck_memberships_role_valid" in membership_check_constraints
    assert "ck_memberships_status_valid" in membership_check_constraints
    assert "ck_memberships_lifecycle_timestamps_consistent" in membership_check_constraints
    assert "ix_users_normalized_email" in user_indexes
    assert "ix_organizations_slug" in organization_indexes
    assert "ix_memberships_organization_id" in membership_indexes
    assert "ix_memberships_user_id" in membership_indexes
    assert "ix_memberships_organization_status" in membership_indexes
    assert "ix_memberships_user_status" in membership_indexes
    assert "ix_memberships_organization_user_status" in membership_indexes


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

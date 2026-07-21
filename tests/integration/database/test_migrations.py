"""Alembic migration integration tests."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from workflowforge_infrastructure.config import DatabaseSettings
from workflowforge_infrastructure.database import create_sync_migration_engine

from tests.integration.database.utils import require_postgresql


@pytest.fixture(autouse=True)
def restore_database_to_migration_head() -> Iterator[None]:
    """Keep migration tests from leaking downgraded schema state."""

    settings = require_postgresql()
    alembic_config = _alembic_config(settings)
    command.upgrade(alembic_config, "head")
    try:
        yield
    finally:
        command.upgrade(alembic_config, "head")
        assert _current_revision(settings) == _head_revision(alembic_config)


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
            "password_credentials",
            "users",
        }
        with engine.connect() as connection:
            version_rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            assert version_rows.scalar_one() == "0005_password_credentials"
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
def test_password_credentials_table_has_expected_columns_and_constraints_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: column for column in inspector.get_columns("password_credentials")
        }
        primary_key = inspector.get_pk_constraint("password_credentials")
        foreign_keys = inspector.get_foreign_keys("password_credentials")
    finally:
        engine.dispose()

    assert set(columns) == {
        "user_id",
        "password_hash",
        "created_at",
        "updated_at",
    }
    assert columns["user_id"]["nullable"] is False
    assert columns["password_hash"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    assert columns["updated_at"]["nullable"] is False
    assert primary_key["constrained_columns"] == ["user_id"]
    assert {
        (foreign_key["referred_table"], tuple(foreign_key["constrained_columns"]))
        for foreign_key in foreign_keys
    } == {("users", ("user_id",))}
    assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"


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


@pytest.mark.integration
def test_migration_fixture_restores_head_before_each_test() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)

    assert _current_revision(settings) == _head_revision(alembic_config)


def _alembic_config(settings: DatabaseSettings) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = settings
    return config


def _head_revision(config: Config) -> str:
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _current_revision(settings: DatabaseSettings) -> str:
    engine = create_sync_migration_engine(settings)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version"))
            return str(revision.scalar_one())
    finally:
        engine.dispose()

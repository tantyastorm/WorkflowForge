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
            "batch_documents",
            "batches",
            "case_comments",
            "case_decisions",
            "case_documents",
            "case_tasks",
            "cases",
            "documents",
            "document_artifacts",
            "document_versions",
            "upload_idempotency",
            "auth_sessions",
            "security_audit_events",
            "memberships",
            "organizations",
            "password_credentials",
            "refresh_tokens",
            "users",
        }
        with engine.connect() as connection:
            version_rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version")
            assert version_rows.scalar_one() == "0011_cases"
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
        "organization_id",
        "display_filename",
        "source_type",
        "source_reference",
        "status",
        "current_version_id",
        "archived_at",
        "archived_by_user_id",
        "created_at",
        "created_by_user_id",
        "updated_at",
        "updated_by_user_id",
        "lock_version",
    }
    assert columns["organization_id"]["nullable"] is False
    assert columns["current_version_id"]["nullable"] is False
    assert "ck_documents_status_valid" in constraints
    assert "ck_documents_source_type_valid" in constraints
    assert "ck_documents_archive_state_consistent" in constraints
    assert "uq_documents_organization_id_id" in unique_constraints
    assert "ix_documents_organization_status" in indexes
    assert "ix_documents_organization_source" in indexes
    assert "ix_documents_organization_updated_at" in indexes


@pytest.mark.integration
def test_document_version_and_artifact_tables_have_expected_constraints_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        version_columns = {
            column["name"]: column for column in inspector.get_columns("document_versions")
        }
        artifact_columns = {
            column["name"]: column for column in inspector.get_columns("document_artifacts")
        }
        version_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("document_versions")
        }
        artifact_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("document_artifacts")
        }
        version_unique = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("document_versions")
        }
        artifact_unique = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("document_artifacts")
        }
        version_indexes = {index["name"] for index in inspector.get_indexes("document_versions")}
        artifact_indexes = {index["name"] for index in inspector.get_indexes("document_artifacts")}
    finally:
        engine.dispose()

    assert set(version_columns) == {
        "id",
        "organization_id",
        "document_id",
        "version_number",
        "original_filename",
        "media_type",
        "byte_size",
        "content_hash",
        "storage_object_key",
        "storage_state",
        "created_at",
        "created_by_user_id",
    }
    assert set(artifact_columns) == {
        "id",
        "organization_id",
        "document_id",
        "document_version_id",
        "artifact_type",
        "media_type",
        "byte_size",
        "content_hash",
        "storage_object_key",
        "metadata",
        "created_at",
        "created_by_user_id",
    }
    assert "ck_document_versions_version_number_positive" in version_checks
    assert "ck_document_versions_byte_size_non_negative" in version_checks
    assert "ck_document_versions_storage_state_valid" in version_checks
    assert "uq_document_versions_document_version" in version_unique
    assert "uq_document_versions_organization_content_hash" in version_unique
    assert "uq_document_versions_organization_storage_key" in version_unique
    assert "ix_document_versions_document_version" in version_indexes
    assert "ix_document_versions_organization_hash" in version_indexes
    assert "ck_document_artifacts_byte_size_non_negative" in artifact_checks
    assert "ck_document_artifacts_artifact_type_valid" in artifact_checks
    assert "uq_document_artifacts_organization_storage_key" in artifact_unique
    assert "ix_document_artifacts_organization_document" in artifact_indexes
    assert "ix_document_artifacts_organization_document_type" in artifact_indexes
    assert artifact_columns["metadata"]["nullable"] is False


@pytest.mark.integration
def test_upload_idempotency_table_has_expected_columns_constraints_and_indexes_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("upload_idempotency")}
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("upload_idempotency")
        }
        unique_constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("upload_idempotency")
        }
        indexes = {index["name"] for index in inspector.get_indexes("upload_idempotency")}
    finally:
        engine.dispose()

    assert set(columns) == {
        "id",
        "organization_id",
        "idempotency_key",
        "request_fingerprint",
        "status",
        "document_id",
        "document_version_id",
        "response_status",
        "outcome",
        "error_code",
        "retryable",
        "created_at",
        "updated_at",
        "expires_at",
    }
    assert columns["organization_id"]["nullable"] is False
    assert columns["idempotency_key"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["retryable"]["nullable"] is False
    assert "ck_upload_idempotency_status_valid" in checks
    assert "ck_upload_idempotency_response_status_valid" in checks
    assert "uq_upload_idempotency_organization_key" in unique_constraints
    assert "ix_upload_idempotency_organization_status" in indexes
    assert "ix_upload_idempotency_expires_at" in indexes


@pytest.mark.integration
def test_batch_tables_have_expected_columns_constraints_and_indexes_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        batch_columns = {column["name"]: column for column in inspector.get_columns("batches")}
        batch_document_columns = {
            column["name"]: column for column in inspector.get_columns("batch_documents")
        }
        batch_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("batches")
        }
        batch_unique = {
            constraint["name"] for constraint in inspector.get_unique_constraints("batches")
        }
        batch_document_unique = {
            constraint["name"] for constraint in inspector.get_unique_constraints("batch_documents")
        }
        batch_indexes = {index["name"] for index in inspector.get_indexes("batches")}
        batch_document_indexes = {
            index["name"] for index in inspector.get_indexes("batch_documents")
        }
    finally:
        engine.dispose()

    assert set(batch_columns) == {
        "id",
        "organization_id",
        "name",
        "description",
        "status",
        "external_reference",
        "created_at",
        "created_by_user_id",
        "updated_at",
        "updated_by_user_id",
        "archived_at",
        "archived_by_user_id",
        "lock_version",
    }
    assert set(batch_document_columns) == {
        "id",
        "organization_id",
        "batch_id",
        "document_id",
        "added_at",
        "added_by_user_id",
    }
    assert "ck_batches_status_valid" in batch_checks
    assert "ck_batches_lock_version_positive" in batch_checks
    assert "uq_batches_organization_id_id" in batch_unique
    assert "uq_batch_documents_batch_document" in batch_document_unique
    assert "ix_batches_organization_status" in batch_indexes
    assert "ix_batches_organization_created_at" in batch_indexes
    assert "ix_batch_documents_organization_batch" in batch_document_indexes
    assert "ix_batch_documents_organization_document" in batch_document_indexes


@pytest.mark.integration
def test_case_tables_have_expected_columns_constraints_and_indexes_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        case_columns = {column["name"]: column for column in inspector.get_columns("cases")}
        case_document_columns = {
            column["name"]: column for column in inspector.get_columns("case_documents")
        }
        case_task_columns = {
            column["name"]: column for column in inspector.get_columns("case_tasks")
        }
        case_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("cases")
        }
        case_task_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("case_tasks")
        }
        case_unique = {
            constraint["name"] for constraint in inspector.get_unique_constraints("cases")
        }
        case_document_unique = {
            constraint["name"] for constraint in inspector.get_unique_constraints("case_documents")
        }
        case_indexes = {index["name"] for index in inspector.get_indexes("cases")}
        case_document_indexes = {index["name"] for index in inspector.get_indexes("case_documents")}
        case_comment_indexes = {index["name"] for index in inspector.get_indexes("case_comments")}
        case_task_indexes = {index["name"] for index in inspector.get_indexes("case_tasks")}
        case_decision_indexes = {index["name"] for index in inspector.get_indexes("case_decisions")}
    finally:
        engine.dispose()

    assert set(case_columns) == {
        "id",
        "organization_id",
        "title",
        "summary",
        "status",
        "priority",
        "external_reference",
        "created_at",
        "created_by_user_id",
        "updated_at",
        "updated_by_user_id",
        "closed_at",
        "closed_by_user_id",
        "archived_at",
        "archived_by_user_id",
        "lock_version",
    }
    assert set(case_document_columns) == {
        "id",
        "organization_id",
        "case_id",
        "document_id",
        "added_at",
        "added_by_user_id",
    }
    assert set(case_task_columns) == {
        "id",
        "organization_id",
        "case_id",
        "title",
        "description",
        "status",
        "assigned_to_user_id",
        "due_at",
        "completed_at",
        "completed_by_user_id",
        "created_at",
        "created_by_user_id",
        "updated_at",
        "updated_by_user_id",
        "lock_version",
    }
    assert "ck_cases_status_valid" in case_checks
    assert "ck_cases_priority_valid" in case_checks
    assert "ck_cases_lock_version_positive" in case_checks
    assert "ck_case_tasks_status_valid" in case_task_checks
    assert "ck_case_tasks_lock_version_positive" in case_task_checks
    assert "uq_cases_organization_id_id" in case_unique
    assert "uq_case_documents_case_document" in case_document_unique
    assert "ix_cases_organization_status" in case_indexes
    assert "ix_cases_organization_priority" in case_indexes
    assert "ix_cases_organization_created_at" in case_indexes
    assert "ix_case_documents_organization_case" in case_document_indexes
    assert "ix_case_comments_organization_case" in case_comment_indexes
    assert "ix_case_tasks_organization_case" in case_task_indexes
    assert "ix_case_decisions_organization_case" in case_decision_indexes


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
def test_session_tables_have_expected_columns_constraints_and_indexes_at_head() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        session_columns = {
            column["name"]: column for column in inspector.get_columns("auth_sessions")
        }
        token_columns = {
            column["name"]: column for column in inspector.get_columns("refresh_tokens")
        }
        session_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("auth_sessions")
        }
        token_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("refresh_tokens")
        }
        token_unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("refresh_tokens")
        }
        session_indexes = {index["name"] for index in inspector.get_indexes("auth_sessions")}
        token_indexes = {index["name"] for index in inspector.get_indexes("refresh_tokens")}
        session_foreign_keys = inspector.get_foreign_keys("auth_sessions")
        token_foreign_keys = inspector.get_foreign_keys("refresh_tokens")
    finally:
        engine.dispose()

    assert set(session_columns) == {
        "id",
        "user_id",
        "created_at",
        "updated_at",
        "expires_at",
        "revoked_at",
    }
    assert set(token_columns) == {
        "id",
        "session_id",
        "token_family_id",
        "token_hash",
        "generation",
        "issued_at",
        "expires_at",
        "used_at",
        "revoked_at",
        "replaced_by_token_id",
    }
    assert session_columns["user_id"]["nullable"] is False
    assert token_columns["token_hash"]["nullable"] is False
    assert token_columns["generation"]["nullable"] is False
    assert "ck_auth_sessions_expires_after_created" in session_checks
    assert "ck_auth_sessions_updated_after_created" in session_checks
    assert "ck_auth_sessions_revoked_after_created" in session_checks
    assert "ck_refresh_tokens_generation_non_negative" in token_checks
    assert "ck_refresh_tokens_expires_after_issued" in token_checks
    assert "ck_refresh_tokens_used_after_issued" in token_checks
    assert "ck_refresh_tokens_revoked_after_issued" in token_checks
    assert "uq_refresh_tokens_token_hash" in token_unique_constraints
    assert "uq_refresh_tokens_session_generation" in token_unique_constraints
    assert "ix_auth_sessions_user_id" in session_indexes
    assert "ix_auth_sessions_user_revoked_expires" in session_indexes
    assert "ix_refresh_tokens_session_id" in token_indexes
    assert "ix_refresh_tokens_token_family_id" in token_indexes
    assert "ix_refresh_tokens_session_current" in token_indexes
    assert {
        (foreign_key["referred_table"], tuple(foreign_key["constrained_columns"]))
        for foreign_key in session_foreign_keys
    } == {("users", ("user_id",))}
    assert any(
        foreign_key["referred_table"] == "auth_sessions"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in token_foreign_keys
    )


@pytest.mark.integration
def test_security_audit_events_table_has_expected_columns_indexes_and_fk_policy() -> None:
    settings = require_postgresql()
    command.upgrade(_alembic_config(settings), "head")

    engine = create_sync_migration_engine(settings)
    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: column for column in inspector.get_columns("security_audit_events")
        }
        indexes = {index["name"] for index in inspector.get_indexes("security_audit_events")}
        foreign_keys = inspector.get_foreign_keys("security_audit_events")
    finally:
        engine.dispose()

    assert set(columns) == {
        "id",
        "event_type",
        "outcome",
        "occurred_at",
        "actor_user_id",
        "organization_id",
        "session_id",
        "request_id",
        "source_ip",
        "user_agent",
        "metadata",
        "created_at",
    }
    assert columns["metadata"]["nullable"] is False
    assert columns["event_type"]["nullable"] is False
    assert "ix_security_audit_events_occurred_at" in indexes
    assert "ix_security_audit_events_actor_user_id" in indexes
    assert "ix_security_audit_events_organization_id" in indexes
    assert "ix_security_audit_events_event_type_outcome" in indexes
    assert {
        (foreign_key["referred_table"], tuple(foreign_key["constrained_columns"]))
        for foreign_key in foreign_keys
    } == {
        ("users", ("actor_user_id",)),
        ("organizations", ("organization_id",)),
        ("auth_sessions", ("session_id",)),
    }
    assert all(foreign_key["options"].get("ondelete") == "SET NULL" for foreign_key in foreign_keys)


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
def test_legacy_document_rows_backfill_first_version_when_owner_is_unambiguous() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0007_security_audit_events")

    organization_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    user_id = "11111111-1111-4111-8111-111111111111"
    membership_id = "22222222-2222-4222-8222-222222222222"
    document_id = "33333333-3333-4333-8333-333333333333"
    now = "2026-01-02T03:04:05+00:00"
    engine = create_sync_migration_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, normalized_email, display_name, is_active, "
                    "created_at, updated_at) VALUES "
                    "(:user_id, 'owner@example.com', 'owner@example.com', "
                    "'Owner', true, :now, :now)"
                ),
                {"user_id": user_id, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) "
                    "VALUES (:organization_id, 'Org', 'org', true, :now, :now)"
                ),
                {"organization_id": organization_id, "now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO memberships (id, user_id, organization_id, role, status, "
                    "invited_at, joined_at, suspended_at, removed_at, created_at, updated_at) "
                    "VALUES (:membership_id, :user_id, :organization_id, 'owner', 'active', "
                    "NULL, :now, NULL, NULL, :now, :now)"
                ),
                {
                    "membership_id": membership_id,
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO documents (id, original_filename, media_type, byte_size, "
                    "content_hash, storage_object_key, status, created_at, updated_at) "
                    "VALUES (:document_id, 'legacy.pdf', 'application/pdf', 123, :hash, "
                    ":storage_key, 'stored', :now, :now)"
                ),
                {
                    "document_id": document_id,
                    "hash": "e" * 64,
                    "storage_key": "documents/sha256/ee/ee/" + "e" * 64,
                    "now": now,
                },
            )
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "head")
    engine = create_sync_migration_engine(settings)
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT d.organization_id, d.display_filename, d.current_version_id, "
                        "v.version_number, v.storage_state, v.storage_object_key "
                        "FROM documents d JOIN document_versions v ON d.current_version_id = v.id "
                        "WHERE d.id = :document_id"
                    ),
                    {"document_id": document_id},
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()

    assert str(row["organization_id"]) == organization_id
    assert row["display_filename"] == "legacy.pdf"
    assert row["version_number"] == 1
    assert row["storage_state"] == "stored"
    assert row["storage_object_key"] == "documents/sha256/ee/ee/" + "e" * 64


@pytest.mark.integration
def test_legacy_document_rows_fail_when_ownership_is_ambiguous() -> None:
    settings = require_postgresql()
    alembic_config = _alembic_config(settings)
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0007_security_audit_events")

    now = "2026-01-02T03:04:05+00:00"
    engine = create_sync_migration_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents (id, original_filename, media_type, byte_size, "
                    "content_hash, storage_object_key, status, created_at, updated_at) "
                    "VALUES ('33333333-3333-4333-8333-333333333333', 'legacy.pdf', "
                    "'application/pdf', 123, :hash, :storage_key, 'registered', :now, :now)"
                ),
                {
                    "hash": "f" * 64,
                    "storage_key": "documents/sha256/ff/ff/" + "f" * 64,
                    "now": now,
                },
            )
        with pytest.raises(RuntimeError, match="ownership is ambiguous"):
            command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM documents"))
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "head")


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

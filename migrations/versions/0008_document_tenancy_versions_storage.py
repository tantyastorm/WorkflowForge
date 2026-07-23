"""Add tenant-owned document versions and storage metadata."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_doc_tenancy_versions"
down_revision: str | None = "0007_security_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Evolve documents into tenant-owned version-aware aggregates."""

    connection = op.get_bind()
    legacy_count = connection.execute(sa.text("SELECT count(*) FROM documents")).scalar_one()

    op.add_column("documents", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("display_filename", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("source_type", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("source_reference", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("current_version_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("archived_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("documents", sa.Column("updated_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("lock_version", sa.Integer(), server_default=sa.text("1"), nullable=True),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_object_key", sa.String(length=255), nullable=False),
        sa.Column("storage_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "version_number > 0",
            name=op.f("ck_document_versions_version_number_positive"),
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name=op.f("ck_document_versions_byte_size_non_negative"),
        ),
        sa.CheckConstraint(
            "storage_state IN ('pending', 'stored', 'failed')",
            name=op.f("ck_document_versions_storage_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_document_versions_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_document_versions_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name=op.f("uq_document_versions_organization_id_id"),
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name=op.f("uq_document_versions_document_version"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "content_hash",
            name=op.f("uq_document_versions_organization_content_hash"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "storage_object_key",
            name=op.f("uq_document_versions_organization_storage_key"),
        ),
    )
    op.create_index(
        "ix_document_versions_document_version",
        "document_versions",
        ["document_id", "version_number"],
    )
    op.create_index(
        "ix_document_versions_organization_hash",
        "document_versions",
        ["organization_id", "content_hash"],
    )

    if legacy_count:
        organization_id, actor_user_id = _resolve_legacy_owner(connection)
        rows = connection.execute(
            sa.text(
                "SELECT id, original_filename, media_type, byte_size, content_hash, "
                "storage_object_key, status, created_at, updated_at FROM documents"
            )
        ).mappings()
        for row in rows:
            version_id = uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO document_versions "
                    "(id, organization_id, document_id, version_number, original_filename, "
                    "media_type, byte_size, content_hash, storage_object_key, storage_state, "
                    "created_at, created_by_user_id) "
                    "VALUES (:id, :organization_id, :document_id, 1, :original_filename, "
                    ":media_type, :byte_size, :content_hash, :storage_object_key, :storage_state, "
                    ":created_at, :created_by_user_id)"
                ),
                {
                    "id": version_id,
                    "organization_id": organization_id,
                    "document_id": row["id"],
                    "original_filename": row["original_filename"],
                    "media_type": row["media_type"],
                    "byte_size": row["byte_size"],
                    "content_hash": row["content_hash"],
                    "storage_object_key": row["storage_object_key"],
                    "storage_state": _legacy_storage_state(row["status"]),
                    "created_at": row["created_at"],
                    "created_by_user_id": actor_user_id,
                },
            )
            connection.execute(
                sa.text(
                    "UPDATE documents SET organization_id = :organization_id, "
                    "display_filename = :display_filename, source_type = 'upload', "
                    "current_version_id = :current_version_id, "
                    "created_by_user_id = :created_by_user_id, "
                    "updated_by_user_id = :updated_by_user_id, lock_version = 1 "
                    "WHERE id = :document_id"
                ),
                {
                    "organization_id": organization_id,
                    "display_filename": row["original_filename"],
                    "current_version_id": version_id,
                    "created_by_user_id": actor_user_id,
                    "updated_by_user_id": actor_user_id,
                    "document_id": row["id"],
                },
            )
    else:
        connection.execute(
            sa.text("UPDATE documents SET lock_version = 1 WHERE lock_version IS NULL")
        )

    op.drop_index(op.f("ix_documents_content_hash"), table_name="documents")
    op.drop_constraint(op.f("uq_documents_content_hash"), "documents", type_="unique")
    op.drop_constraint(op.f("uq_documents_storage_object_key"), "documents", type_="unique")
    op.drop_constraint(op.f("ck_documents_byte_size_non_negative"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_status_valid"), "documents", type_="check")

    op.alter_column("documents", "organization_id", nullable=False)
    op.alter_column("documents", "display_filename", nullable=False)
    op.alter_column("documents", "source_type", nullable=False)
    op.alter_column("documents", "current_version_id", nullable=False)
    op.alter_column("documents", "created_by_user_id", nullable=False)
    op.alter_column("documents", "updated_by_user_id", nullable=False)
    op.alter_column("documents", "lock_version", server_default=None, nullable=False)

    op.create_check_constraint(
        op.f("ck_documents_status_valid"),
        "documents",
        "status IN ('registered', 'stored', 'failed', 'archived')",
    )
    op.create_check_constraint(
        op.f("ck_documents_source_type_valid"),
        "documents",
        "source_type IN ('upload', 'import', 'system')",
    )
    op.create_check_constraint(
        op.f("ck_documents_lock_version_positive"),
        "documents",
        "lock_version > 0",
    )
    op.create_check_constraint(
        op.f("ck_documents_archive_state_consistent"),
        "documents",
        "(status = 'archived' AND archived_at IS NOT NULL "
        "AND archived_by_user_id IS NOT NULL) OR "
        "(status <> 'archived' AND archived_at IS NULL "
        "AND archived_by_user_id IS NULL)",
    )
    op.create_foreign_key(
        op.f("fk_documents_organization_id_organizations"),
        "documents",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_documents_archived_by_user_id_users"),
        "documents",
        "users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_documents_created_by_user_id_users"),
        "documents",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_documents_updated_by_user_id_users"),
        "documents",
        "users",
        ["updated_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_documents_organization_id_id"),
        "documents",
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_document_versions_organization_document_documents"),
        "document_versions",
        "documents",
        ["organization_id", "document_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        op.f("fk_documents_organization_current_version_document_versions"),
        "documents",
        "document_versions",
        ["organization_id", "current_version_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_index(
        "ix_documents_organization_status",
        "documents",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_documents_organization_source",
        "documents",
        ["organization_id", "source_type"],
    )
    op.create_index(
        "ix_documents_organization_updated_at",
        "documents",
        ["organization_id", "updated_at"],
    )

    op.drop_column("documents", "original_filename")
    op.drop_column("documents", "media_type")
    op.drop_column("documents", "byte_size")
    op.drop_column("documents", "content_hash")
    op.drop_column("documents", "storage_object_key")

    op.create_table(
        "document_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("storage_object_key", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "byte_size >= 0",
            name=op.f("ck_document_artifacts_byte_size_non_negative"),
        ),
        sa.CheckConstraint(
            "artifact_type IN ('original', 'preview', 'text', 'export', 'other')",
            name=op.f("ck_document_artifacts_artifact_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_document_artifacts_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_document_artifacts_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_document_artifacts_organization_document_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name=op.f("fk_document_artifacts_organization_version_document_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_artifacts")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name=op.f("uq_document_artifacts_organization_id_id"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "storage_object_key",
            name=op.f("uq_document_artifacts_organization_storage_key"),
        ),
    )
    op.create_index(
        "ix_document_artifacts_organization_document",
        "document_artifacts",
        ["organization_id", "document_id"],
    )
    op.create_index(
        "ix_document_artifacts_organization_document_type",
        "document_artifacts",
        ["organization_id", "document_id", "artifact_type"],
    )


def downgrade() -> None:
    """Return document persistence to the Phase 2 metadata table."""

    op.drop_index(
        "ix_document_artifacts_organization_document_type",
        table_name="document_artifacts",
    )
    op.drop_index("ix_document_artifacts_organization_document", table_name="document_artifacts")
    op.drop_table("document_artifacts")

    op.add_column(
        "documents", sa.Column("storage_object_key", sa.String(length=255), nullable=True)
    )
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("byte_size", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("media_type", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("original_filename", sa.String(length=255), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE documents d SET "
            "original_filename = v.original_filename, media_type = v.media_type, "
            "byte_size = v.byte_size, content_hash = v.content_hash, "
            "storage_object_key = v.storage_object_key "
            "FROM document_versions v WHERE d.current_version_id = v.id"
        )
    )
    op.alter_column("documents", "original_filename", nullable=False)
    op.alter_column("documents", "media_type", nullable=False)
    op.alter_column("documents", "byte_size", nullable=False)
    op.alter_column("documents", "content_hash", nullable=False)
    op.alter_column("documents", "storage_object_key", nullable=False)

    op.drop_constraint(
        op.f("fk_documents_organization_current_version_document_versions"),
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_document_versions_organization_document_documents"),
        "document_versions",
        type_="foreignkey",
    )
    op.drop_index("ix_documents_organization_updated_at", table_name="documents")
    op.drop_index("ix_documents_organization_source", table_name="documents")
    op.drop_index("ix_documents_organization_status", table_name="documents")
    op.drop_constraint(op.f("uq_documents_organization_id_id"), "documents", type_="unique")
    op.drop_constraint(
        op.f("fk_documents_updated_by_user_id_users"), "documents", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_documents_created_by_user_id_users"), "documents", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_documents_archived_by_user_id_users"), "documents", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_documents_organization_id_organizations"), "documents", type_="foreignkey"
    )
    op.drop_constraint(op.f("ck_documents_archive_state_consistent"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_lock_version_positive"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_source_type_valid"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_status_valid"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_byte_size_non_negative"),
        "documents",
        "byte_size >= 0",
    )
    op.create_check_constraint(
        op.f("ck_documents_status_valid"),
        "documents",
        "status IN ('registered', 'stored', 'failed')",
    )
    op.create_unique_constraint(
        op.f("uq_documents_content_hash"),
        "documents",
        ["content_hash"],
    )
    op.create_unique_constraint(
        op.f("uq_documents_storage_object_key"),
        "documents",
        ["storage_object_key"],
    )
    op.create_index(op.f("ix_documents_content_hash"), "documents", ["content_hash"])

    op.drop_column("documents", "lock_version")
    op.drop_column("documents", "updated_by_user_id")
    op.drop_column("documents", "created_by_user_id")
    op.drop_column("documents", "archived_by_user_id")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "current_version_id")
    op.drop_column("documents", "source_reference")
    op.drop_column("documents", "source_type")
    op.drop_column("documents", "display_filename")
    op.drop_column("documents", "organization_id")

    op.drop_index("ix_document_versions_organization_hash", table_name="document_versions")
    op.drop_index("ix_document_versions_document_version", table_name="document_versions")
    op.drop_table("document_versions")


def _resolve_legacy_owner(connection: sa.Connection) -> tuple[object, object]:
    organizations = connection.execute(sa.text("SELECT id FROM organizations")).scalars().all()
    if len(organizations) != 1:
        msg = (
            "Legacy documents exist but ownership is ambiguous. "
            "Ensure exactly one organization exists or migrate legacy documents "
            "manually before 0008."
        )
        raise RuntimeError(msg)
    owner_users = (
        connection.execute(
            sa.text(
                "SELECT user_id FROM memberships "
                "WHERE organization_id = :organization_id AND role = 'owner' "
                "AND status = 'active'"
            ),
            {"organization_id": organizations[0]},
        )
        .scalars()
        .all()
    )
    if len(owner_users) == 1:
        return organizations[0], owner_users[0]
    users = connection.execute(sa.text("SELECT id FROM users")).scalars().all()
    if len(users) == 1:
        return organizations[0], users[0]
    msg = (
        "Legacy documents exist but actor metadata is ambiguous. "
        "Ensure exactly one active owner or exactly one user exists before 0008."
    )
    raise RuntimeError(msg)


def _legacy_storage_state(status: str) -> str:
    if status == "stored":
        return "stored"
    if status == "failed":
        return "failed"
    return "pending"

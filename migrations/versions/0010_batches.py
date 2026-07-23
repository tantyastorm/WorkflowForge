"""Create batches tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_batches"
down_revision: str | None = "0009_upload_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-scoped batches and memberships."""

    op.create_table(
        "batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'archived')",
            name=op.f("ck_batches_status_valid"),
        ),
        sa.CheckConstraint("lock_version > 0", name=op.f("ck_batches_lock_version_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_batches_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_batches_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_batches_updated_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["archived_by_user_id"],
            ["users.id"],
            name=op.f("fk_batches_archived_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batches")),
        sa.UniqueConstraint("organization_id", "id", name="uq_batches_organization_id_id"),
    )
    op.create_index("ix_batches_organization_status", "batches", ["organization_id", "status"])
    op.create_index(
        "ix_batches_organization_created_at",
        "batches",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "batch_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_batch_documents_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "batch_id"],
            ["batches.organization_id", "batches.id"],
            name=op.f("fk_batch_documents_organization_batch_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_batch_documents_organization_document_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name=op.f("fk_batch_documents_added_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_documents")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_batch_documents_organization_id_id",
        ),
        sa.UniqueConstraint("batch_id", "document_id", name="uq_batch_documents_batch_document"),
    )
    op.create_index(
        "ix_batch_documents_organization_batch",
        "batch_documents",
        ["organization_id", "batch_id"],
    )
    op.create_index(
        "ix_batch_documents_organization_document",
        "batch_documents",
        ["organization_id", "document_id"],
    )


def downgrade() -> None:
    """Remove tenant-scoped batches and memberships."""

    op.drop_index("ix_batch_documents_organization_document", table_name="batch_documents")
    op.drop_index("ix_batch_documents_organization_batch", table_name="batch_documents")
    op.drop_table("batch_documents")
    op.drop_index("ix_batches_organization_created_at", table_name="batches")
    op.drop_index("ix_batches_organization_status", table_name="batches")
    op.drop_table("batches")

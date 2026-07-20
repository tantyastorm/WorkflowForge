"""Create document metadata table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_documents"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create document metadata persistence."""

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_object_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size >= 0", name=op.f("ck_documents_byte_size_non_negative")),
        sa.CheckConstraint(
            "status IN ('registered', 'stored', 'failed')",
            name=op.f("ck_documents_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_documents_content_hash")),
        sa.UniqueConstraint("storage_object_key", name=op.f("uq_documents_storage_object_key")),
    )
    op.create_index(op.f("ix_documents_content_hash"), "documents", ["content_hash"], unique=False)


def downgrade() -> None:
    """Remove document metadata persistence."""

    op.drop_index(op.f("ix_documents_content_hash"), table_name="documents")
    op.drop_table("documents")

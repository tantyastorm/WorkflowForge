"""Create upload idempotency table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_upload_idempotency"
down_revision: str | None = "0008_doc_tenancy_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-scoped upload idempotency persistence."""

    op.create_table(
        "upload_idempotency",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'failed')",
            name=op.f("ck_upload_idempotency_status_valid"),
        ),
        sa.CheckConstraint(
            "response_status IS NULL OR response_status >= 100",
            name=op.f("ck_upload_idempotency_response_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_upload_idempotency_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_upload_idempotency_organization_document_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name=op.f("fk_upload_idempotency_organization_version_document_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_idempotency")),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name=op.f("uq_upload_idempotency_organization_key"),
        ),
    )
    op.create_index(
        "ix_upload_idempotency_organization_status",
        "upload_idempotency",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_upload_idempotency_expires_at",
        "upload_idempotency",
        ["expires_at"],
    )


def downgrade() -> None:
    """Remove upload idempotency persistence."""

    op.drop_index("ix_upload_idempotency_expires_at", table_name="upload_idempotency")
    op.drop_index("ix_upload_idempotency_organization_status", table_name="upload_idempotency")
    op.drop_table("upload_idempotency")

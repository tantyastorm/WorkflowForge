"""Create cases tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_cases"
down_revision: str | None = "0010_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-scoped cases and related tables."""

    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=4000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'archived')", name=op.f("ck_cases_status_valid")
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')", name=op.f("ck_cases_priority_valid")
        ),
        sa.CheckConstraint("lock_version > 0", name=op.f("ck_cases_lock_version_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_cases_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_cases_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_cases_updated_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"],
            ["users.id"],
            name=op.f("fk_cases_closed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["archived_by_user_id"],
            ["users.id"],
            name=op.f("fk_cases_archived_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("organization_id", "id", name="uq_cases_organization_id_id"),
    )
    op.create_index("ix_cases_organization_status", "cases", ["organization_id", "status"])
    op.create_index("ix_cases_organization_priority", "cases", ["organization_id", "priority"])
    op.create_index("ix_cases_organization_created_at", "cases", ["organization_id", "created_at"])
    op.create_table(
        "case_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_documents_organization_case_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_case_documents_organization_document_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_documents_added_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_documents")),
        sa.UniqueConstraint("case_id", "document_id", name="uq_case_documents_case_document"),
    )
    op.create_index(
        "ix_case_documents_organization_case", "case_documents", ["organization_id", "case_id"]
    )
    op.create_table(
        "case_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(length=4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_comments_organization_case_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_comments_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_comments_updated_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_comments")),
    )
    op.create_index(
        "ix_case_comments_organization_case", "case_comments", ["organization_id", "case_id"]
    )
    op.create_table(
        "case_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'completed', 'cancelled')", name=op.f("ck_case_tasks_status_valid")
        ),
        sa.CheckConstraint("lock_version > 0", name=op.f("ck_case_tasks_lock_version_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_tasks_organization_case_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"],
            ["users.id"],
            name=op.f("fk_case_tasks_assigned_to_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_tasks_completed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_tasks_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_tasks_updated_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_tasks")),
    )
    op.create_index("ix_case_tasks_organization_case", "case_tasks", ["organization_id", "case_id"])
    op.create_table(
        "case_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("decision_type", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.String(length=4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_decisions_organization_case_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_case_decisions_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_decisions")),
    )
    op.create_index(
        "ix_case_decisions_organization_case", "case_decisions", ["organization_id", "case_id"]
    )


def downgrade() -> None:
    """Remove tenant-scoped cases and related tables."""

    op.drop_index("ix_case_decisions_organization_case", table_name="case_decisions")
    op.drop_table("case_decisions")
    op.drop_index("ix_case_tasks_organization_case", table_name="case_tasks")
    op.drop_table("case_tasks")
    op.drop_index("ix_case_comments_organization_case", table_name="case_comments")
    op.drop_table("case_comments")
    op.drop_index("ix_case_documents_organization_case", table_name="case_documents")
    op.drop_table("case_documents")
    op.drop_index("ix_cases_organization_created_at", table_name="cases")
    op.drop_index("ix_cases_organization_priority", table_name="cases")
    op.drop_index("ix_cases_organization_status", table_name="cases")
    op.drop_table("cases")

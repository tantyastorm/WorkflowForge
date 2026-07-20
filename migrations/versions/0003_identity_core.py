"""Create users and organizations tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_identity_core"
down_revision: str | None = "0002_create_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create identity and organization persistence."""

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("normalized_email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(is_active = true AND disabled_at IS NULL) OR "
            "(is_active = false AND disabled_at IS NOT NULL)",
            name=op.f("ck_users_active_disabled_timestamp_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("normalized_email", name=op.f("uq_users_normalized_email")),
    )
    op.create_index(op.f("ix_users_normalized_email"), "users", ["normalized_email"])

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(is_active = true AND deactivated_at IS NULL) OR "
            "(is_active = false AND deactivated_at IS NOT NULL)",
            name=op.f("ck_organizations_active_deactivated_timestamp_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"])


def downgrade() -> None:
    """Remove identity and organization persistence."""

    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
    op.drop_index(op.f("ix_users_normalized_email"), table_name="users")
    op.drop_table("users")

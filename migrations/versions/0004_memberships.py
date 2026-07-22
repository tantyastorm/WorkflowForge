"""Create memberships table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_memberships"
down_revision: str | None = "0003_identity_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create organization membership persistence."""

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'operator', 'reviewer', 'auditor')",
            name=op.f("ck_memberships_role_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'removed')",
            name=op.f("ck_memberships_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'invited' AND invited_at IS NOT NULL AND joined_at IS NULL "
            "AND suspended_at IS NULL AND removed_at IS NULL) OR "
            "(status = 'active' AND joined_at IS NOT NULL AND suspended_at IS NULL "
            "AND removed_at IS NULL) OR "
            "(status = 'suspended' AND joined_at IS NOT NULL AND suspended_at IS NOT NULL "
            "AND removed_at IS NULL) OR "
            "(status = 'removed' AND removed_at IS NOT NULL)",
            name=op.f("ck_memberships_lifecycle_timestamps_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name=op.f("uq_memberships_organization_user"),
        ),
    )
    op.create_index(op.f("ix_memberships_organization_id"), "memberships", ["organization_id"])
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"])
    op.create_index(
        "ix_memberships_organization_status",
        "memberships",
        ["organization_id", "status"],
    )
    op.create_index("ix_memberships_user_status", "memberships", ["user_id", "status"])
    op.create_index(
        "ix_memberships_organization_user_status",
        "memberships",
        ["organization_id", "user_id", "status"],
    )


def downgrade() -> None:
    """Remove organization membership persistence."""

    op.drop_index("ix_memberships_organization_user_status", table_name="memberships")
    op.drop_index("ix_memberships_user_status", table_name="memberships")
    op.drop_index("ix_memberships_organization_status", table_name="memberships")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_organization_id"), table_name="memberships")
    op.drop_table("memberships")

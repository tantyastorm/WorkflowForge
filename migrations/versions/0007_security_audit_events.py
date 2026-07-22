"""Create security audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_security_audit_events"
down_revision: str | None = "0006_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only security audit event persistence."""

    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("source_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_security_audit_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_security_audit_events_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_security_audit_events_session_id_auth_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_audit_events")),
    )
    op.create_index(
        "ix_security_audit_events_occurred_at",
        "security_audit_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_security_audit_events_actor_user_id",
        "security_audit_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_security_audit_events_organization_id",
        "security_audit_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_security_audit_events_event_type_outcome",
        "security_audit_events",
        ["event_type", "outcome"],
    )


def downgrade() -> None:
    """Remove security audit event persistence."""

    op.drop_index(
        "ix_security_audit_events_event_type_outcome",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_organization_id",
        table_name="security_audit_events",
    )
    op.drop_index(
        "ix_security_audit_events_actor_user_id",
        table_name="security_audit_events",
    )
    op.drop_index("ix_security_audit_events_occurred_at", table_name="security_audit_events")
    op.drop_table("security_audit_events")

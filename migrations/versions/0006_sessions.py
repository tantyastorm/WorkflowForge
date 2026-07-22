"""Create authenticated sessions and refresh tokens."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_sessions"
down_revision: str | None = "0005_password_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable session and refresh-token rotation persistence."""

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_auth_sessions_expires_after_created"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_auth_sessions_updated_after_created"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_auth_sessions_revoked_after_created"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_user_revoked_expires",
        "auth_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "generation >= 0",
            name=op.f("ck_refresh_tokens_generation_non_negative"),
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name=op.f("ck_refresh_tokens_expires_after_issued"),
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR used_at >= issued_at",
            name=op.f("ck_refresh_tokens_used_after_issued"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name=op.f("ck_refresh_tokens_revoked_after_issued"),
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_token_id_refresh_tokens"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_refresh_tokens_session_id_auth_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
        sa.UniqueConstraint(
            "session_id",
            "generation",
            name=op.f("uq_refresh_tokens_session_generation"),
        ),
    )
    op.create_index(op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"])
    op.create_index(
        op.f("ix_refresh_tokens_token_family_id"),
        "refresh_tokens",
        ["token_family_id"],
    )
    op.create_index(
        "ix_refresh_tokens_session_current",
        "refresh_tokens",
        ["session_id", "used_at", "revoked_at"],
    )


def downgrade() -> None:
    """Remove durable session and refresh-token rotation persistence."""

    op.drop_index("ix_refresh_tokens_session_current", table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_auth_sessions_user_revoked_expires", table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")

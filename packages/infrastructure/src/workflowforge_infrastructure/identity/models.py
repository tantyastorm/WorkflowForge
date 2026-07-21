"""SQLAlchemy models for identity and tenancy persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from workflowforge_domain.identity.entities import (
    DISPLAY_NAME_MAX_LENGTH,
    ORGANIZATION_NAME_MAX_LENGTH,
)
from workflowforge_domain.identity.value_objects import (
    EMAIL_MAX_LENGTH,
    ORGANIZATION_SLUG_MAX_LENGTH,
)

from workflowforge_infrastructure.database.base import Base

PASSWORD_HASH_MAX_LENGTH = 1024


class UserRecord(Base):
    """Infrastructure-owned users table."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(is_active = true AND disabled_at IS NULL) OR "
            "(is_active = false AND disabled_at IS NOT NULL)",
            name="active_disabled_timestamp_consistent",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), nullable=False)
    normalized_email: Mapped[str] = mapped_column(
        String(EMAIL_MAX_LENGTH),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(DISPLAY_NAME_MAX_LENGTH),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrganizationRecord(Base):
    """Infrastructure-owned organizations table."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "(is_active = true AND deactivated_at IS NULL) OR "
            "(is_active = false AND deactivated_at IS NOT NULL)",
            name="active_deactivated_timestamp_consistent",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(ORGANIZATION_NAME_MAX_LENGTH), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(ORGANIZATION_SLUG_MAX_LENGTH),
        nullable=False,
        unique=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class MembershipRecord(Base):
    """Infrastructure-owned memberships table."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_user"),
        CheckConstraint(
            "role IN ('owner', 'admin', 'operator', 'reviewer', 'auditor')",
            name="role_valid",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'removed')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'invited' AND invited_at IS NOT NULL AND joined_at IS NULL "
            "AND suspended_at IS NULL AND removed_at IS NULL) OR "
            "(status = 'active' AND joined_at IS NOT NULL AND suspended_at IS NULL "
            "AND removed_at IS NULL) OR "
            "(status = 'suspended' AND joined_at IS NOT NULL AND suspended_at IS NOT NULL "
            "AND removed_at IS NULL) OR "
            "(status = 'removed' AND removed_at IS NOT NULL)",
            name="lifecycle_timestamps_consistent",
        ),
        Index("ix_memberships_organization_id", "organization_id"),
        Index("ix_memberships_user_id", "user_id"),
        Index("ix_memberships_organization_status", "organization_id", "status"),
        Index("ix_memberships_user_status", "user_id", "status"),
        Index("ix_memberships_organization_user_status", "organization_id", "user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordCredentialRecord(Base):
    """Infrastructure-owned password credentials table."""

    __tablename__ = "password_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

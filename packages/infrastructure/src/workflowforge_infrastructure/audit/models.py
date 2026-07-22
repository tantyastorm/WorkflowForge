"""SQLAlchemy models for durable audit persistence."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from workflowforge_domain.audit import (
    AUDIT_REQUEST_ID_MAX_LENGTH,
    AUDIT_SOURCE_IP_MAX_LENGTH,
    AUDIT_USER_AGENT_MAX_LENGTH,
)

from workflowforge_infrastructure.database.base import Base

AUDIT_EVENT_TYPE_MAX_LENGTH = 128
AUDIT_OUTCOME_MAX_LENGTH = 32


class SecurityAuditEventRecord(Base):
    """Infrastructure-owned append-only security audit event row."""

    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_occurred_at", "occurred_at"),
        Index("ix_security_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_security_audit_events_organization_id", "organization_id"),
        Index("ix_security_audit_events_event_type_outcome", "event_type", "outcome"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(AUDIT_EVENT_TYPE_MAX_LENGTH), nullable=False)
    outcome: Mapped[str] = mapped_column(String(AUDIT_OUTCOME_MAX_LENGTH), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_id: Mapped[str | None] = mapped_column(
        String(AUDIT_REQUEST_ID_MAX_LENGTH),
        nullable=True,
    )
    source_ip: Mapped[str | None] = mapped_column(
        String(AUDIT_SOURCE_IP_MAX_LENGTH),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(AUDIT_USER_AGENT_MAX_LENGTH),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

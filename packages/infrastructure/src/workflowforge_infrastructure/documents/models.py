"""SQLAlchemy models for document metadata."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from workflowforge_infrastructure.database.base import Base


class DocumentRecord(Base):
    """Infrastructure-owned document aggregate table."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('registered', 'stored', 'failed', 'archived')",
            name="status_valid",
        ),
        CheckConstraint(
            "source_type IN ('upload', 'import', 'system')",
            name="source_type_valid",
        ),
        CheckConstraint("lock_version > 0", name="lock_version_positive"),
        CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL "
            "AND archived_by_user_id IS NOT NULL) OR "
            "(status <> 'archived' AND archived_at IS NULL "
            "AND archived_by_user_id IS NULL)",
            name="archive_state_consistent",
        ),
        UniqueConstraint("organization_id", "id", name="uq_documents_organization_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "current_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_documents_organization_current_version_document_versions",
            ondelete="RESTRICT",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_documents_organization_status", "organization_id", "status"),
        Index("ix_documents_organization_source", "organization_id", "source_type"),
        Index("ix_documents_organization_updated_at", "organization_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_version_id: Mapped[UUID] = mapped_column(nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class DocumentVersionRecord(Base):
    """Infrastructure-owned immutable document version table."""

    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        CheckConstraint(
            "storage_state IN ('pending', 'stored', 'failed')",
            name="storage_state_valid",
        ),
        UniqueConstraint("organization_id", "id", name="uq_document_versions_organization_id_id"),
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_version"
        ),
        UniqueConstraint(
            "organization_id",
            "content_hash",
            name="uq_document_versions_organization_content_hash",
        ),
        UniqueConstraint(
            "organization_id",
            "storage_object_key",
            name="uq_document_versions_organization_storage_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_versions_organization_document_documents",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_document_versions_document_version", "document_id", "version_number"),
        Index("ix_document_versions_organization_hash", "organization_id", "content_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class DocumentArtifactRecord(Base):
    """Infrastructure-owned document artifact table."""

    __tablename__ = "document_artifacts"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        CheckConstraint(
            "artifact_type IN ('original', 'preview', 'text', 'export', 'other')",
            name="artifact_type_valid",
        ),
        UniqueConstraint("organization_id", "id", name="uq_document_artifacts_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "storage_object_key",
            name="uq_document_artifacts_organization_storage_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_artifacts_organization_document_documents",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_document_artifacts_organization_version_document_versions",
            ondelete="CASCADE",
        ),
        Index("ix_document_artifacts_organization_document", "organization_id", "document_id"),
        Index(
            "ix_document_artifacts_organization_document_type",
            "organization_id",
            "document_id",
            "artifact_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

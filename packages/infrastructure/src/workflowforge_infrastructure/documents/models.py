"""SQLAlchemy models for document metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from workflowforge_infrastructure.database.base import Base


class DocumentRecord(Base):
    """Infrastructure-owned document metadata table."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        CheckConstraint(
            "status IN ('registered', 'stored', 'failed')",
            name="status_valid",
        ),
        UniqueConstraint("content_hash", name="uq_documents_content_hash"),
        UniqueConstraint("storage_object_key", name="uq_documents_storage_object_key"),
        Index("ix_documents_content_hash", "content_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

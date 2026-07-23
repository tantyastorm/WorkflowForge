"""Batch persistence adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from workflowforge_application.batches import BatchListFilter, BatchListPage
from workflowforge_application.documents import DocumentNotFoundError
from workflowforge_domain.batches import Batch, BatchDocument, BatchDocumentId, BatchId, BatchStatus
from workflowforge_domain.documents import DocumentId

from workflowforge_infrastructure.database.base import Base


class BatchRecord(Base):
    """Batch ORM record."""

    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed', 'archived')", name="status_valid"),
        CheckConstraint("lock_version > 0", name="lock_version_positive"),
        UniqueConstraint("organization_id", "id", name="uq_batches_organization_id_id"),
        Index("ix_batches_organization_status", "organization_id", "status"),
        Index("ix_batches_organization_created_at", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class BatchDocumentRecord(Base):
    """Batch-document membership ORM record."""

    __tablename__ = "batch_documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_batch_documents_organization_id_id"),
        UniqueConstraint("batch_id", "document_id", name="uq_batch_documents_batch_document"),
        ForeignKeyConstraint(
            ["organization_id", "batch_id"],
            ["batches.organization_id", "batches.id"],
            name="fk_batch_documents_organization_batch_batches",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_batch_documents_organization_document_documents",
            ondelete="CASCADE",
        ),
        Index("ix_batch_documents_organization_batch", "organization_id", "batch_id"),
        Index("ix_batch_documents_organization_document", "organization_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    added_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class SqlAlchemyBatchRepository:
    """SQLAlchemy batch repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, batch: Batch) -> Batch:
        record = _record_from_batch(batch)
        self._session.add(record)
        await self._session.flush()
        return _batch_from_record(record)

    async def get(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        record = await self._batch_record(organization_id=organization_id, batch_id=batch_id)
        return _batch_from_record(record) if record is not None else None

    async def get_for_update(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        result = await self._session.execute(
            select(BatchRecord)
            .where(BatchRecord.organization_id == organization_id, BatchRecord.id == batch_id.value)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        return _batch_from_record(record) if record is not None else None

    async def list_batches(
        self,
        *,
        organization_id: UUID,
        query: BatchListFilter,
    ) -> BatchListPage:
        statement = select(BatchRecord).where(BatchRecord.organization_id == organization_id)
        if query.status is not None:
            statement = statement.where(BatchRecord.status == query.status.value)
        elif query.archived is True:
            statement = statement.where(BatchRecord.status == BatchStatus.ARCHIVED.value)
        elif query.archived is False:
            statement = statement.where(BatchRecord.status != BatchStatus.ARCHIVED.value)
        if query.name is not None:
            statement = statement.where(BatchRecord.name.ilike(f"%{query.name}%"))
        total_result = await self._session.execute(
            select(func.count()).select_from(statement.subquery())
        )
        result = await self._session.execute(
            statement.order_by(BatchRecord.created_at.desc(), BatchRecord.id.desc())
            .limit(query.limit)
            .offset(query.offset)
        )
        return BatchListPage(
            items=[_batch_from_record(record) for record in result.scalars()],
            total=int(total_result.scalar_one()),
            limit=query.limit,
            offset=query.offset,
        )

    async def update(self, batch: Batch) -> Batch:
        await self._session.execute(
            update(BatchRecord)
            .where(
                BatchRecord.organization_id == batch.organization_id,
                BatchRecord.id == batch.id.value,
                BatchRecord.lock_version == batch.lock_version - 1,
            )
            .values(
                name=batch.name,
                description=batch.description,
                status=batch.status.value,
                external_reference=batch.external_reference,
                updated_at=batch.updated_at,
                updated_by_user_id=batch.updated_by_user_id,
                archived_at=batch.archived_at,
                archived_by_user_id=batch.archived_by_user_id,
                lock_version=batch.lock_version,
            )
        )
        await self._session.flush()
        return batch

    async def add_document(self, membership: BatchDocument) -> BatchDocument:
        record = _record_from_membership(membership)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._membership_record(
                organization_id=membership.organization_id,
                batch_id=membership.batch_id,
                document_id=membership.document_id,
            )
            if existing is not None:
                return _membership_from_record(existing)
            raise DocumentNotFoundError("Document was not found.") from exc
        return _membership_from_record(record)

    async def remove_document(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
        document_id: DocumentId,
    ) -> bool:
        result = await self._session.execute(
            delete(BatchDocumentRecord).where(
                BatchDocumentRecord.organization_id == organization_id,
                BatchDocumentRecord.batch_id == batch_id.value,
                BatchDocumentRecord.document_id == document_id.value,
            )
        )
        await self._session.flush()
        return bool(cast("Any", result).rowcount)

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
    ) -> list[BatchDocument]:
        result = await self._session.execute(
            select(BatchDocumentRecord)
            .where(
                BatchDocumentRecord.organization_id == organization_id,
                BatchDocumentRecord.batch_id == batch_id.value,
            )
            .order_by(BatchDocumentRecord.added_at.desc(), BatchDocumentRecord.id.desc())
        )
        return [_membership_from_record(record) for record in result.scalars()]

    async def _batch_record(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
    ) -> BatchRecord | None:
        result = await self._session.execute(
            select(BatchRecord).where(
                BatchRecord.organization_id == organization_id,
                BatchRecord.id == batch_id.value,
            )
        )
        return result.scalar_one_or_none()

    async def _membership_record(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
        document_id: DocumentId,
    ) -> BatchDocumentRecord | None:
        result = await self._session.execute(
            select(BatchDocumentRecord).where(
                BatchDocumentRecord.organization_id == organization_id,
                BatchDocumentRecord.batch_id == batch_id.value,
                BatchDocumentRecord.document_id == document_id.value,
            )
        )
        return result.scalar_one_or_none()


def _record_from_batch(batch: Batch) -> BatchRecord:
    return BatchRecord(
        id=batch.id.value,
        organization_id=batch.organization_id,
        name=batch.name,
        description=batch.description,
        status=batch.status.value,
        external_reference=batch.external_reference,
        created_at=batch.created_at,
        created_by_user_id=batch.created_by_user_id,
        updated_at=batch.updated_at,
        updated_by_user_id=batch.updated_by_user_id,
        archived_at=batch.archived_at,
        archived_by_user_id=batch.archived_by_user_id,
        lock_version=batch.lock_version,
    )


def _batch_from_record(record: BatchRecord) -> Batch:
    return Batch(
        id=BatchId(record.id),
        organization_id=record.organization_id,
        name=record.name,
        description=record.description,
        status=BatchStatus(record.status),
        external_reference=record.external_reference,
        created_at=record.created_at.astimezone(UTC),
        created_by_user_id=record.created_by_user_id,
        updated_at=record.updated_at.astimezone(UTC),
        updated_by_user_id=record.updated_by_user_id,
        archived_at=record.archived_at.astimezone(UTC) if record.archived_at else None,
        archived_by_user_id=record.archived_by_user_id,
        lock_version=record.lock_version,
    )


def _record_from_membership(membership: BatchDocument) -> BatchDocumentRecord:
    return BatchDocumentRecord(
        id=membership.id.value,
        organization_id=membership.organization_id,
        batch_id=membership.batch_id.value,
        document_id=membership.document_id.value,
        added_at=membership.added_at,
        added_by_user_id=membership.added_by_user_id,
    )


def _membership_from_record(record: BatchDocumentRecord) -> BatchDocument:
    return BatchDocument(
        id=BatchDocumentId(record.id),
        organization_id=record.organization_id,
        batch_id=BatchId(record.batch_id),
        document_id=DocumentId(record.document_id),
        added_at=record.added_at.astimezone(UTC),
        added_by_user_id=record.added_by_user_id,
    )

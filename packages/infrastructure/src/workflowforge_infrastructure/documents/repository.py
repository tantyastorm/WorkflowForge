"""SQLAlchemy document repository."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.documents import (
    DocumentRepository,
    DuplicateDocumentContentError,
)
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    DocumentStatus,
    StorageObjectKey,
)

from workflowforge_infrastructure.documents.models import DocumentRecord


class SqlAlchemyDocumentRepository(DocumentRepository):
    """SQLAlchemy implementation of the document repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> Document:
        """Persist document metadata."""

        record = _record_from_document(document)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Document content is already registered."
            raise DuplicateDocumentContentError(msg) from exc
        return _document_from_record(record)

    async def get_by_id(self, document_id: DocumentId) -> Document | None:
        """Return a document by ID, when present."""

        record = await self._session.get(DocumentRecord, document_id.value)
        if record is None:
            return None
        return _document_from_record(record)

    async def get_by_content_hash(self, content_hash: ContentHash) -> Document | None:
        """Return a document by deterministic content hash, when present."""

        result = await self._session.execute(
            select(DocumentRecord).where(DocumentRecord.content_hash == content_hash.value)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _document_from_record(record)


def _record_from_document(document: Document) -> DocumentRecord:
    return DocumentRecord(
        id=document.id.value,
        original_filename=document.original_filename,
        media_type=document.media_type,
        byte_size=document.byte_size,
        content_hash=document.content_hash.value,
        storage_object_key=document.storage_object_key.value,
        status=document.status.value,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _document_from_record(record: DocumentRecord) -> Document:
    return Document(
        id=DocumentId(record.id),
        original_filename=record.original_filename,
        media_type=record.media_type,
        byte_size=record.byte_size,
        content_hash=ContentHash(record.content_hash),
        storage_object_key=StorageObjectKey(record.storage_object_key),
        status=DocumentStatus(record.status),
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
    )

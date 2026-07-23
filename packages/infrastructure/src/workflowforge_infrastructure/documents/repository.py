"""SQLAlchemy document repository."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.documents import (
    DocumentListFilter,
    DocumentProjection,
    DocumentRepository,
    DuplicateDocumentContentError,
)
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentId,
    DocumentSourceType,
    DocumentStatus,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
)

from workflowforge_infrastructure.documents.models import (
    DocumentArtifactRecord,
    DocumentRecord,
    DocumentVersionRecord,
)


class SqlAlchemyDocumentRepository(DocumentRepository):
    """SQLAlchemy implementation of the tenant-aware document repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_document(self, document: Document, version: DocumentVersion) -> Document:
        """Persist a document and its initial version metadata."""

        document_record = _record_from_document(document)
        version_record = _record_from_version(version)
        self._session.add(document_record)
        self._session.add(version_record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Document content is already registered for this tenant."
            raise DuplicateDocumentContentError(msg) from exc
        return _document_from_record(document_record)

    async def get_document(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> Document | None:
        """Return a tenant-scoped document by ID, when present."""

        result = await self._session.execute(
            select(DocumentRecord).where(
                DocumentRecord.organization_id == organization_id,
                DocumentRecord.id == document_id.value,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _document_from_record(record)

    async def get_document_for_update(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> Document | None:
        """Return a tenant-scoped document with a row lock, when present."""

        result = await self._session.execute(
            select(DocumentRecord)
            .where(
                DocumentRecord.organization_id == organization_id,
                DocumentRecord.id == document_id.value,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _document_from_record(record)

    async def find_document_by_tenant_content_hash(
        self,
        *,
        organization_id: UUID,
        content_hash: ContentHash,
    ) -> Document | None:
        """Return the tenant document that owns exact bytes, when present."""

        result = await self._session.execute(
            select(DocumentRecord)
            .join(
                DocumentVersionRecord, DocumentRecord.current_version_id == DocumentVersionRecord.id
            )
            .where(
                DocumentRecord.organization_id == organization_id,
                DocumentVersionRecord.organization_id == organization_id,
                DocumentVersionRecord.content_hash == content_hash.value,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _document_from_record(record)

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        query: DocumentListFilter,
    ) -> list[DocumentProjection]:
        """Return tenant-scoped document projections."""

        statement = select(DocumentRecord).where(DocumentRecord.organization_id == organization_id)
        if query.status is not None:
            statement = statement.where(DocumentRecord.status == query.status.value)
        elif not query.include_archived:
            statement = statement.where(DocumentRecord.status != DocumentStatus.ARCHIVED.value)
        if query.source_type is not None:
            statement = statement.where(DocumentRecord.source_type == query.source_type.value)
        statement = statement.order_by(DocumentRecord.updated_at.desc(), DocumentRecord.id).limit(
            query.limit
        )
        statement = statement.offset(query.offset)
        result = await self._session.execute(statement)
        return [_projection_from_record(record) for record in result.scalars()]

    async def archive_document(self, document: Document) -> Document:
        """Persist document archive state."""

        await self._persist_document_state(document)
        return document

    async def add_version(self, version: DocumentVersion) -> DocumentVersion:
        """Persist a document version."""

        record = _record_from_version(version)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Document content is already registered for this tenant."
            raise DuplicateDocumentContentError(msg) from exc
        return _version_from_record(record)

    async def get_version(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion | None:
        """Return a tenant-scoped version by ID, when present."""

        result = await self._session.execute(
            select(DocumentVersionRecord).where(
                DocumentVersionRecord.organization_id == organization_id,
                DocumentVersionRecord.document_id == document_id.value,
                DocumentVersionRecord.id == version_id.value,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _version_from_record(record)

    async def list_versions(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> list[DocumentVersion]:
        """Return versions for a tenant-scoped document."""

        result = await self._session.execute(
            select(DocumentVersionRecord)
            .where(
                DocumentVersionRecord.organization_id == organization_id,
                DocumentVersionRecord.document_id == document_id.value,
            )
            .order_by(DocumentVersionRecord.version_number)
        )
        return [_version_from_record(record) for record in result.scalars()]

    async def set_current_version(
        self,
        *,
        document: Document,
        version: DocumentVersion,
    ) -> Document:
        """Persist a new current-version reference on a document."""

        if (
            version.organization_id != document.organization_id
            or version.document_id != document.id
        ):
            msg = "Current version must match document tenant and ID."
            raise ValueError(msg)
        await self._persist_document_state(document)
        return document

    async def add_artifact(self, artifact: DocumentArtifact) -> DocumentArtifact:
        """Persist metadata for a real stored artifact."""

        record = _record_from_artifact(artifact)
        self._session.add(record)
        await self._session.flush()
        return _artifact_from_record(record)

    async def get_artifact(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        artifact_id: DocumentArtifactId,
    ) -> DocumentArtifact | None:
        """Return a tenant-scoped artifact by ID, when present."""

        result = await self._session.execute(
            select(DocumentArtifactRecord).where(
                DocumentArtifactRecord.organization_id == organization_id,
                DocumentArtifactRecord.document_id == document_id.value,
                DocumentArtifactRecord.id == artifact_id.value,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _artifact_from_record(record)

    async def _persist_document_state(self, document: Document) -> None:
        await self._session.execute(
            update(DocumentRecord)
            .where(
                DocumentRecord.organization_id == document.organization_id,
                DocumentRecord.id == document.id.value,
                DocumentRecord.lock_version == document.lock_version - 1,
            )
            .values(
                display_filename=document.display_filename,
                source_type=document.source_type.value,
                source_reference=document.source_reference,
                status=document.status.value,
                current_version_id=document.current_version_id.value,
                archived_at=document.archived_at,
                archived_by_user_id=document.archived_by_user_id,
                updated_at=document.updated_at,
                updated_by_user_id=document.updated_by_user_id,
                lock_version=document.lock_version,
            )
        )
        await self._session.flush()


def _record_from_document(document: Document) -> DocumentRecord:
    return DocumentRecord(
        id=document.id.value,
        organization_id=document.organization_id,
        display_filename=document.display_filename,
        source_type=document.source_type.value,
        source_reference=document.source_reference,
        status=document.status.value,
        current_version_id=document.current_version_id.value,
        archived_at=document.archived_at,
        archived_by_user_id=document.archived_by_user_id,
        created_at=document.created_at,
        created_by_user_id=document.created_by_user_id,
        updated_at=document.updated_at,
        updated_by_user_id=document.updated_by_user_id,
        lock_version=document.lock_version,
    )


def _document_from_record(record: DocumentRecord) -> Document:
    return Document(
        id=DocumentId(record.id),
        organization_id=record.organization_id,
        display_filename=record.display_filename,
        source_type=DocumentSourceType(record.source_type),
        source_reference=record.source_reference,
        status=DocumentStatus(record.status),
        current_version_id=DocumentVersionId(record.current_version_id),
        archived_at=record.archived_at.astimezone(UTC) if record.archived_at is not None else None,
        archived_by_user_id=record.archived_by_user_id,
        created_at=record.created_at.astimezone(UTC),
        created_by_user_id=record.created_by_user_id,
        updated_at=record.updated_at.astimezone(UTC),
        updated_by_user_id=record.updated_by_user_id,
        lock_version=record.lock_version,
    )


def _record_from_version(version: DocumentVersion) -> DocumentVersionRecord:
    return DocumentVersionRecord(
        id=version.id.value,
        organization_id=version.organization_id,
        document_id=version.document_id.value,
        version_number=version.version_number,
        original_filename=version.original_filename,
        media_type=version.media_type,
        byte_size=version.byte_size,
        content_hash=version.content_hash.value,
        storage_object_key=version.storage_object_key.value,
        storage_state=version.storage_state.value,
        created_at=version.created_at,
        created_by_user_id=version.created_by_user_id,
    )


def _version_from_record(record: DocumentVersionRecord) -> DocumentVersion:
    return DocumentVersion(
        id=DocumentVersionId(record.id),
        organization_id=record.organization_id,
        document_id=DocumentId(record.document_id),
        version_number=record.version_number,
        original_filename=record.original_filename,
        media_type=record.media_type,
        byte_size=record.byte_size,
        content_hash=ContentHash(record.content_hash),
        storage_object_key=StorageObjectKey(record.storage_object_key),
        storage_state=DocumentStorageState(record.storage_state),
        created_at=record.created_at.astimezone(UTC),
        created_by_user_id=record.created_by_user_id,
    )


def _record_from_artifact(artifact: DocumentArtifact) -> DocumentArtifactRecord:
    return DocumentArtifactRecord(
        id=artifact.id.value,
        organization_id=artifact.organization_id,
        document_id=artifact.document_id.value,
        document_version_id=(
            artifact.document_version_id.value if artifact.document_version_id is not None else None
        ),
        artifact_type=artifact.artifact_type.value,
        media_type=artifact.media_type,
        byte_size=artifact.byte_size,
        content_hash=artifact.content_hash.value if artifact.content_hash is not None else None,
        storage_object_key=artifact.storage_object_key.value,
        metadata_json=dict(artifact.metadata),
        created_at=artifact.created_at,
        created_by_user_id=artifact.created_by_user_id,
    )


def _artifact_from_record(record: DocumentArtifactRecord) -> DocumentArtifact:
    return DocumentArtifact(
        id=DocumentArtifactId(record.id),
        organization_id=record.organization_id,
        document_id=DocumentId(record.document_id),
        document_version_id=(
            DocumentVersionId(record.document_version_id)
            if record.document_version_id is not None
            else None
        ),
        artifact_type=DocumentArtifactType(record.artifact_type),
        media_type=record.media_type,
        byte_size=record.byte_size,
        content_hash=ContentHash(record.content_hash) if record.content_hash is not None else None,
        storage_object_key=StorageObjectKey(record.storage_object_key),
        metadata=record.metadata_json,
        created_at=record.created_at.astimezone(UTC),
        created_by_user_id=record.created_by_user_id,
    )


def _projection_from_record(record: DocumentRecord) -> DocumentProjection:
    return DocumentProjection(
        id=DocumentId(record.id),
        organization_id=record.organization_id,
        display_filename=record.display_filename,
        source_type=DocumentSourceType(record.source_type),
        status=DocumentStatus(record.status),
        current_version_id=DocumentVersionId(record.current_version_id),
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        lock_version=record.lock_version,
    )

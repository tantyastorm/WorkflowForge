"""SQLAlchemy document repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.documents import (
    DocumentListFilter,
    DocumentListPage,
    DocumentProjection,
    DocumentRepository,
    DuplicateDocumentContentError,
    UploadIdempotencyRecord,
    UploadIdempotencyRepository,
    UploadIdempotencyStatus,
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
    UploadIdempotencyRecordModel,
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
    ) -> DocumentListPage:
        """Return tenant-scoped document projections."""

        base = (
            select(DocumentRecord, DocumentVersionRecord)
            .join(
                DocumentVersionRecord,
                DocumentRecord.current_version_id == DocumentVersionRecord.id,
            )
            .where(
                DocumentRecord.organization_id == organization_id,
                DocumentVersionRecord.organization_id == organization_id,
            )
        )
        if query.status is not None:
            base = base.where(DocumentRecord.status == query.status.value)
        elif query.archived is True:
            base = base.where(DocumentRecord.status == DocumentStatus.ARCHIVED.value)
        elif query.archived is False:
            base = base.where(DocumentRecord.status != DocumentStatus.ARCHIVED.value)
        if query.source_type is not None:
            base = base.where(DocumentRecord.source_type == query.source_type.value)
        if query.media_type is not None:
            base = base.where(DocumentVersionRecord.media_type == query.media_type)
        if query.created_from is not None:
            base = base.where(DocumentRecord.created_at >= query.created_from)
        if query.created_to is not None:
            base = base.where(DocumentRecord.created_at <= query.created_to)
        if query.filename is not None:
            base = base.where(DocumentRecord.display_filename.ilike(f"%{query.filename}%"))
        total_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(total_result.scalar_one())
        statement = base.order_by(DocumentRecord.created_at.desc(), DocumentRecord.id.desc()).limit(
            query.limit
        )
        statement = statement.offset(query.offset)
        result = await self._session.execute(statement)
        return DocumentListPage(
            items=[_projection_from_record(record, version) for record, version in result.tuples()],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

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

    async def list_artifacts(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> list[DocumentArtifact]:
        """Return artifacts for a tenant-scoped document."""

        result = await self._session.execute(
            select(DocumentArtifactRecord)
            .where(
                DocumentArtifactRecord.organization_id == organization_id,
                DocumentArtifactRecord.document_id == document_id.value,
            )
            .order_by(DocumentArtifactRecord.created_at.desc(), DocumentArtifactRecord.id.desc())
        )
        return [_artifact_from_record(record) for record in result.scalars()]

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

    async def mark_version_stored(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        """Mark a version's storage state as stored."""

        return await self._mark_version_storage_state(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
            storage_state=DocumentStorageState.STORED,
        )

    async def mark_version_failed(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        """Mark a version's storage state as failed."""

        return await self._mark_version_storage_state(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
            storage_state=DocumentStorageState.FAILED,
        )

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

    async def _mark_version_storage_state(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
        storage_state: DocumentStorageState,
    ) -> DocumentVersion:
        record = await self._version_record(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
        )
        if record is None:
            msg = "Document version does not exist."
            raise ValueError(msg)
        record.storage_state = storage_state.value
        await self._session.flush()
        return _version_from_record(record)

    async def _version_record(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersionRecord | None:
        result = await self._session.execute(
            select(DocumentVersionRecord).where(
                DocumentVersionRecord.organization_id == organization_id,
                DocumentVersionRecord.document_id == document_id.value,
                DocumentVersionRecord.id == version_id.value,
            )
        )
        return result.scalar_one_or_none()


class SqlAlchemyUploadIdempotencyRepository(UploadIdempotencyRepository):
    """SQLAlchemy implementation of upload idempotency persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        now: datetime,
        expires_at: datetime,
    ) -> UploadIdempotencyRecord:
        """Reserve a tenant-scoped idempotency key or return the existing record."""

        record = UploadIdempotencyRecordModel(
            id=uuid4(),
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            request_fingerprint=None,
            status=UploadIdempotencyStatus.IN_PROGRESS.value,
            document_id=None,
            document_version_id=None,
            response_status=None,
            outcome=None,
            error_code=None,
            retryable=False,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get(
                organization_id=organization_id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            return existing
        return _idempotency_from_record(record)

    async def get(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> UploadIdempotencyRecord | None:
        """Return a tenant-scoped idempotency record."""

        record = await self._record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            return None
        return _idempotency_from_record(record)

    async def mark_in_progress(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        now: datetime,
        expires_at: datetime,
    ) -> UploadIdempotencyRecord:
        """Mark a retryable failed idempotency record as in-progress."""

        record = await self._required_record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if record.status != UploadIdempotencyStatus.FAILED.value or not record.retryable:
            msg = "Only retryable failed upload idempotency records can be retried."
            raise ValueError(msg)
        record.status = UploadIdempotencyStatus.IN_PROGRESS.value
        record.response_status = None
        record.outcome = None
        record.error_code = None
        record.retryable = False
        record.updated_at = now
        record.expires_at = expires_at
        await self._session.flush()
        return _idempotency_from_record(record)

    async def finalize_fingerprint(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist the final request fingerprint."""

        record = await self._required_record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        record.request_fingerprint = request_fingerprint
        record.updated_at = now
        await self._session.flush()
        return _idempotency_from_record(record)

    async def complete(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        document_id: DocumentId,
        document_version_id: DocumentVersionId,
        response_status: int,
        outcome: str,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist a completed idempotent response."""

        record = await self._required_record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        record.request_fingerprint = request_fingerprint
        record.status = UploadIdempotencyStatus.COMPLETED.value
        record.document_id = document_id.value
        record.document_version_id = document_version_id.value
        record.response_status = response_status
        record.outcome = outcome
        record.error_code = None
        record.retryable = False
        record.updated_at = now
        await self._session.flush()
        return _idempotency_from_record(record)

    async def fail(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str | None,
        error_code: str,
        response_status: int,
        retryable: bool,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist a failed idempotent response."""

        record = await self._required_record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        record.request_fingerprint = request_fingerprint
        record.status = UploadIdempotencyStatus.FAILED.value
        record.response_status = response_status
        record.error_code = error_code
        record.outcome = None
        record.retryable = retryable
        record.updated_at = now
        await self._session.flush()
        return _idempotency_from_record(record)

    async def _required_record(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> UploadIdempotencyRecordModel:
        record = await self._record(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if record is None:
            msg = "Upload idempotency record does not exist."
            raise ValueError(msg)
        return record

    async def _record(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> UploadIdempotencyRecordModel | None:
        result = await self._session.execute(
            select(UploadIdempotencyRecordModel).where(
                UploadIdempotencyRecordModel.organization_id == organization_id,
                UploadIdempotencyRecordModel.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()


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


def _projection_from_record(
    record: DocumentRecord,
    version: DocumentVersionRecord,
) -> DocumentProjection:
    return DocumentProjection(
        id=DocumentId(record.id),
        organization_id=record.organization_id,
        display_filename=record.display_filename,
        source_type=DocumentSourceType(record.source_type),
        status=DocumentStatus(record.status),
        current_version_id=DocumentVersionId(record.current_version_id),
        media_type=version.media_type,
        byte_size=version.byte_size,
        storage_state=version.storage_state,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        lock_version=record.lock_version,
    )


def _idempotency_from_record(record: UploadIdempotencyRecordModel) -> UploadIdempotencyRecord:
    return UploadIdempotencyRecord(
        organization_id=record.organization_id,
        idempotency_key=record.idempotency_key,
        request_fingerprint=record.request_fingerprint,
        status=UploadIdempotencyStatus(record.status),
        document_id=DocumentId(record.document_id) if record.document_id is not None else None,
        document_version_id=(
            DocumentVersionId(record.document_version_id)
            if record.document_version_id is not None
            else None
        ),
        response_status=record.response_status,
        outcome=record.outcome,
        error_code=record.error_code,
        retryable=record.retryable,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        expires_at=record.expires_at.astimezone(UTC),
    )

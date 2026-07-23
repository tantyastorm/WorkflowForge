"""Document application services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import BinaryIO, cast
from uuid import UUID, uuid4

from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome, AuditRequestContext
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentId,
    DocumentSourceType,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
    assert_artifact_consistent,
)
from workflowforge_domain.identity import Permission

from workflowforge_application.audit import AuditRecorder
from workflowforge_application.authorization import AuthorizationPolicy, TenantContext
from workflowforge_application.documents.errors import (
    DocumentNotFoundError,
    DuplicateDocumentContentError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    ObjectStorageUnavailableError,
    UploadValidationError,
)
from workflowforge_application.documents.ports import (
    DocumentListFilter,
    DocumentProjection,
    DocumentRepository,
    ObjectStorage,
    PromoteObjectRequest,
    PutTempObjectRequest,
    UploadIdempotencyRecord,
    UploadIdempotencyRepository,
    UploadIdempotencyStatus,
)
from workflowforge_application.documents.upload_validation import (
    MAX_UPLOAD_BYTES,
    AsyncUploadStream,
    NormalizedUploadMetadata,
    StreamedUpload,
    normalize_upload_metadata,
    request_fingerprint,
    stream_upload,
    validate_idempotency_key,
    validate_streamed_content,
)
from workflowforge_application.identity.ports import IdGenerator, TransactionManager


@dataclass(frozen=True, slots=True)
class DocumentRegistrationCommand:
    """Input for registering document metadata."""

    display_filename: str
    media_type: str
    byte_size: int
    content_hash: str
    source_type: DocumentSourceType = DocumentSourceType.UPLOAD
    source_reference: str | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class DocumentVersionCreationCommand:
    """Input for creating version metadata."""

    document_id: DocumentId
    original_filename: str
    media_type: str
    byte_size: int
    content_hash: str
    storage_state: DocumentStorageState = DocumentStorageState.PENDING
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class DocumentArtifactRegistrationCommand:
    """Input for registering stored artifact metadata."""

    document_id: DocumentId
    document_version_id: DocumentVersionId | None
    artifact_type: DocumentArtifactType
    media_type: str
    byte_size: int
    storage_object_key: StorageObjectKey
    content_hash: str | None = None
    metadata: Mapping[str, object] | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    """Input for uploading one document."""

    filename: str | None
    declared_media_type: str | None
    stream: AsyncUploadStream
    idempotency_key: str
    audit_context: AuditRequestContext | None = None


class UploadDocumentOutcome(StrEnum):
    """Document upload result outcome."""

    CREATED = "created"
    DUPLICATE = "duplicate"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True, slots=True)
class UploadDocumentResult:
    """Application upload result DTO."""

    document: Document
    current_version: DocumentVersion
    outcome: UploadDocumentOutcome
    duplicate: bool
    idempotent_replay: bool
    response_status: int


class DocumentService:
    """Use cases for tenant-owned document metadata."""

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        transaction: TransactionManager | None = None,
        authorization: AuthorizationPolicy | None = None,
        audit: AuditRecorder | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self._repository = repository
        self._transaction = transaction
        self._authorization = authorization or AuthorizationPolicy()
        self._audit = audit
        self._ids = ids

    async def register_document(
        self,
        command: DocumentRegistrationCommand,
        *,
        tenant: TenantContext,
        now: datetime | None = None,
    ) -> Document:
        """Register document metadata idempotently by tenant content hash."""

        self._authorization.require(tenant, Permission.DOCUMENT_WRITE)
        timestamp = _now(now)
        content_hash = ContentHash(command.content_hash)
        existing = await self._repository.find_document_by_tenant_content_hash(
            organization_id=tenant.organization_id,
            content_hash=content_hash,
        )
        if existing is not None:
            return existing

        document_id = DocumentId(_new_uuid(self._ids))
        version = DocumentVersion.create(
            id=DocumentVersionId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            document_id=document_id,
            version_number=1,
            original_filename=command.display_filename,
            media_type=command.media_type,
            byte_size=command.byte_size,
            content_hash=content_hash,
            storage_state=DocumentStorageState.PENDING,
            created_at=timestamp,
            created_by_user_id=tenant.user_id,
        )
        document = Document.register(
            id=document_id,
            organization_id=tenant.organization_id,
            display_filename=command.display_filename,
            source_type=command.source_type,
            source_reference=command.source_reference,
            current_version=version,
            created_by_user_id=tenant.user_id,
            now=timestamp,
        )

        try:
            saved = await self._repository.add_document(document, version)
            await self._record_document_event(
                AuditEventType.DOCUMENT_REGISTERED,
                tenant=tenant,
                target_id=saved.id.value,
                request_context=command.audit_context,
                now=timestamp,
                metadata={"source_type": saved.source_type.value},
            )
            await _commit(self._transaction)
            return saved
        except DuplicateDocumentContentError:
            await _rollback(self._transaction)
            duplicate = await self._repository.find_document_by_tenant_content_hash(
                organization_id=tenant.organization_id,
                content_hash=content_hash,
            )
            if duplicate is not None:
                return duplicate
            raise
        except Exception:
            await _rollback(self._transaction)
            raise

    async def get_document(self, document_id: DocumentId, *, tenant: TenantContext) -> Document:
        """Return a tenant-scoped document by ID or raise not-found."""

        self._authorization.require(tenant, Permission.DOCUMENT_READ)
        document = await self._repository.get_document(
            organization_id=tenant.organization_id,
            document_id=document_id,
        )
        if document is None:
            msg = "Document was not found."
            raise DocumentNotFoundError(msg)
        return document

    async def list_documents(
        self,
        *,
        tenant: TenantContext,
        query: DocumentListFilter | None = None,
    ) -> list[DocumentProjection]:
        """Return tenant-scoped document projections."""

        self._authorization.require(tenant, Permission.DOCUMENT_READ)
        return await self._repository.list_documents(
            organization_id=tenant.organization_id,
            query=query or DocumentListFilter(),
        )

    async def create_version(
        self,
        command: DocumentVersionCreationCommand,
        *,
        tenant: TenantContext,
        now: datetime | None = None,
    ) -> DocumentVersion:
        """Create version metadata and update the document current-version pointer."""

        self._authorization.require(tenant, Permission.DOCUMENT_VERSION_CREATE)
        timestamp = _now(now)
        document = await self._repository.get_document_for_update(
            organization_id=tenant.organization_id,
            document_id=command.document_id,
        )
        if document is None:
            msg = "Document was not found."
            raise DocumentNotFoundError(msg)
        versions = await self._repository.list_versions(
            organization_id=tenant.organization_id,
            document_id=command.document_id,
        )
        version = DocumentVersion.create(
            id=DocumentVersionId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            document_id=command.document_id,
            version_number=len(versions) + 1,
            original_filename=command.original_filename,
            media_type=command.media_type,
            byte_size=command.byte_size,
            content_hash=ContentHash(command.content_hash),
            storage_state=command.storage_state,
            created_at=timestamp,
            created_by_user_id=tenant.user_id,
        )
        updated = document.set_current_version(version, actor_user_id=tenant.user_id, now=timestamp)
        try:
            saved = await self._repository.add_version(version)
            await self._repository.set_current_version(document=updated, version=saved)
            await self._record_document_event(
                AuditEventType.DOCUMENT_VERSION_CREATED,
                tenant=tenant,
                target_id=document.id.value,
                request_context=command.audit_context,
                now=timestamp,
                metadata={"version_id": saved.id.value, "version_number": saved.version_number},
            )
            await _commit(self._transaction)
            return saved
        except Exception:
            await _rollback(self._transaction)
            raise

    async def get_version(
        self,
        *,
        tenant: TenantContext,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        """Return a tenant-scoped document version."""

        self._authorization.require(tenant, Permission.DOCUMENT_VERSION_READ)
        version = await self._repository.get_version(
            organization_id=tenant.organization_id,
            document_id=document_id,
            version_id=version_id,
        )
        if version is None:
            msg = "Document version was not found."
            raise DocumentNotFoundError(msg)
        return version

    async def archive_document(
        self,
        document_id: DocumentId,
        *,
        tenant: TenantContext,
        now: datetime | None = None,
        audit_context: AuditRequestContext | None = None,
    ) -> Document:
        """Archive a tenant-scoped document."""

        self._authorization.require(tenant, Permission.DOCUMENT_ARCHIVE)
        timestamp = _now(now)
        document = await self._repository.get_document_for_update(
            organization_id=tenant.organization_id,
            document_id=document_id,
        )
        if document is None:
            msg = "Document was not found."
            raise DocumentNotFoundError(msg)
        archived = document.archive(actor_user_id=tenant.user_id, now=timestamp)
        try:
            saved = await self._repository.archive_document(archived)
            await self._record_document_event(
                AuditEventType.DOCUMENT_ARCHIVED,
                tenant=tenant,
                target_id=saved.id.value,
                request_context=audit_context,
                now=timestamp,
            )
            await _commit(self._transaction)
            return saved
        except Exception:
            await _rollback(self._transaction)
            raise

    async def register_artifact(
        self,
        command: DocumentArtifactRegistrationCommand,
        *,
        tenant: TenantContext,
        now: datetime | None = None,
    ) -> DocumentArtifact:
        """Register metadata for a real stored artifact."""

        self._authorization.require(tenant, Permission.ARTIFACT_READ)
        timestamp = _now(now)
        document = await self.get_document(command.document_id, tenant=tenant)
        version = None
        if command.document_version_id is not None:
            version = await self.get_version(
                tenant=tenant,
                document_id=command.document_id,
                version_id=command.document_version_id,
            )
        artifact = DocumentArtifact.create(
            id=DocumentArtifactId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            document_id=command.document_id,
            document_version_id=command.document_version_id,
            artifact_type=command.artifact_type,
            media_type=command.media_type,
            byte_size=command.byte_size,
            content_hash=(
                ContentHash(command.content_hash) if command.content_hash is not None else None
            ),
            storage_object_key=command.storage_object_key,
            metadata=command.metadata or {},
            created_at=timestamp,
            created_by_user_id=tenant.user_id,
        )
        assert_artifact_consistent(document=document, artifact=artifact, version=version)
        try:
            saved = await self._repository.add_artifact(artifact)
            await self._record_document_event(
                AuditEventType.DOCUMENT_ARTIFACT_REGISTERED,
                tenant=tenant,
                target_id=document.id.value,
                request_context=command.audit_context,
                now=timestamp,
                metadata={
                    "artifact_id": saved.id.value,
                    "artifact_type": saved.artifact_type.value,
                },
            )
            await _commit(self._transaction)
            return saved
        except Exception:
            await _rollback(self._transaction)
            raise

    async def _record_document_event(
        self,
        event_type: AuditEventType,
        *,
        tenant: TenantContext,
        target_id: UUID,
        request_context: AuditRequestContext | None,
        now: datetime,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            AuditEvent.create(
                id=_new_uuid(self._ids),
                event_type=event_type,
                outcome=AuditOutcome.SUCCESS,
                occurred_at=now,
                actor_user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                request_context=request_context,
                metadata={"target_type": "document", "target_id": target_id, **(metadata or {})},
            )
        )


class UploadDocument:
    """Orchestrate tenant-scoped document upload."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        idempotency: UploadIdempotencyRepository,
        storage: ObjectStorage,
        transaction: TransactionManager,
        audit: AuditRecorder | None = None,
        ids: IdGenerator | None = None,
        max_bytes: int = MAX_UPLOAD_BYTES,
        idempotency_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self._documents = documents
        self._idempotency = idempotency
        self._storage = storage
        self._transaction = transaction
        self._audit = audit
        self._ids = ids
        self._max_bytes = max_bytes
        self._idempotency_ttl = idempotency_ttl
        self._authorization = AuthorizationPolicy()

    async def __call__(
        self,
        command: UploadDocumentCommand,
        *,
        tenant: TenantContext,
        now: datetime | None = None,
    ) -> UploadDocumentResult:
        """Upload one document for a tenant."""

        self._authorization.require(tenant, Permission.DOCUMENT_WRITE)
        timestamp = _now(now)
        key = validate_idempotency_key(command.idempotency_key)
        existing_record = await self._idempotency.get(
            organization_id=tenant.organization_id,
            idempotency_key=key,
        )
        if existing_record is not None:
            return await self._handle_existing_record(
                command=command,
                tenant=tenant,
                record=existing_record,
            )

        await self._idempotency.reserve(
            organization_id=tenant.organization_id,
            idempotency_key=key,
            now=timestamp,
            expires_at=timestamp + self._idempotency_ttl,
        )
        await self._transaction.commit()
        await self._record_upload_event(
            AuditEventType.DOCUMENT_UPLOAD_STARTED,
            tenant=tenant,
            request_context=command.audit_context,
            now=timestamp,
            metadata={"idempotency_replay": False},
        )
        return await self._process_reserved_upload(command=command, tenant=tenant, key=key)

    async def _process_reserved_upload(
        self,
        *,
        command: UploadDocumentCommand,
        tenant: TenantContext,
        key: str,
    ) -> UploadDocumentResult:
        temp_key = StorageObjectKey.for_temporary_upload(
            organization_id=tenant.organization_id,
            upload_id=_new_uuid(self._ids),
        )
        metadata: NormalizedUploadMetadata | None = None
        streamed: StreamedUpload | None = None
        fingerprint: str | None = None
        try:
            metadata, streamed, fingerprint = await self._prepare_upload(command)
            await self._idempotency.finalize_fingerprint(
                organization_id=tenant.organization_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                now=_now(None),
            )
            await self._storage.put_temp_stream(
                PutTempObjectRequest(
                    key=temp_key,
                    body=cast("BinaryIO", streamed.body),
                    media_type=metadata.media_type,
                )
            )
            await self._transaction.commit()
        except UploadValidationError as exc:
            if streamed is not None:
                streamed.body.close()
            await self._idempotency.fail(
                organization_id=tenant.organization_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                error_code=exc.code,
                response_status=422,
                retryable=False,
                now=_now(None),
            )
            await self._transaction.commit()
            await self._record_failed_upload(command, tenant=tenant, error_code=exc.code)
            raise
        except Exception as exc:
            if streamed is not None:
                streamed.body.close()
            await self._delete_temp_best_effort(temp_key)
            await self._idempotency.fail(
                organization_id=tenant.organization_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                error_code="object_storage_unavailable",
                response_status=503,
                retryable=True,
                now=_now(None),
            )
            await self._transaction.commit()
            await self._record_failed_upload(
                command,
                tenant=tenant,
                error_code="object_storage_unavailable",
            )
            raise ObjectStorageUnavailableError("Object storage is unavailable.") from exc

        if metadata is None or streamed is None or fingerprint is None:
            raise RuntimeError("Upload preparation did not produce metadata.")

        duplicate_result = await self._complete_duplicate_if_present(
            command=command,
            tenant=tenant,
            idempotency_key=key,
            fingerprint=fingerprint,
            temp_key=temp_key,
            content_hash=streamed.content_hash,
            byte_size=streamed.byte_size,
        )
        if duplicate_result is not None:
            streamed.body.close()
            return duplicate_result

        document, version = self._new_document_pair(
            tenant=tenant,
            metadata=metadata,
            content_hash=streamed.content_hash,
            byte_size=streamed.byte_size,
            now=_now(None),
        )
        try:
            document = await self._documents.add_document(document, version)
            await self._transaction.commit()
        except DuplicateDocumentContentError:
            await self._transaction.rollback()
            duplicate = await self._documents.find_document_by_tenant_content_hash(
                organization_id=tenant.organization_id,
                content_hash=streamed.content_hash,
            )
            if duplicate is None:
                raise
            result = await self._complete_duplicate(
                command=command,
                tenant=tenant,
                idempotency_key=key,
                fingerprint=fingerprint,
                temp_key=temp_key,
                duplicate=duplicate,
                byte_size=streamed.byte_size,
            )
            streamed.body.close()
            return result

        try:
            stored_document, stored_version = await self._promote_new_document(
                document=document,
                version=version,
                tenant=tenant,
                temp_key=temp_key,
                media_type=metadata.media_type,
                byte_size=streamed.byte_size,
                content_hash=streamed.content_hash,
            )
            await self._idempotency.complete(
                organization_id=tenant.organization_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                document_id=stored_document.id,
                document_version_id=stored_version.id,
                response_status=201,
                outcome=UploadDocumentOutcome.CREATED.value,
                now=_now(None),
            )
            await self._transaction.commit()
            await self._record_upload_event(
                AuditEventType.DOCUMENT_STORAGE_SUCCEEDED,
                tenant=tenant,
                request_context=command.audit_context,
                now=_now(None),
                metadata={"document_id": stored_document.id.value, "byte_size": streamed.byte_size},
            )
            streamed.body.close()
            return UploadDocumentResult(
                document=stored_document,
                current_version=stored_version,
                outcome=UploadDocumentOutcome.CREATED,
                duplicate=False,
                idempotent_replay=False,
                response_status=201,
            )
        except Exception as exc:
            streamed.body.close()
            await self._mark_upload_storage_failed(
                command=command,
                tenant=tenant,
                idempotency_key=key,
                fingerprint=fingerprint,
                document=document,
                version=version,
            )
            raise ObjectStorageUnavailableError("Object storage is unavailable.") from exc

    async def _handle_existing_record(
        self,
        *,
        command: UploadDocumentCommand,
        tenant: TenantContext,
        record: UploadIdempotencyRecord,
    ) -> UploadDocumentResult:
        if record.status is UploadIdempotencyStatus.IN_PROGRESS:
            raise IdempotencyInProgressError("Upload is already in progress.")
        if record.status is UploadIdempotencyStatus.COMPLETED:
            await self._assert_replay_fingerprint(command=command, record=record)
            return await self._replay_completed(record, tenant=tenant)
        if record.status is UploadIdempotencyStatus.FAILED and not record.retryable:
            if record.request_fingerprint is not None:
                await self._assert_replay_fingerprint(command=command, record=record)
            raise UploadValidationError(
                record.error_code or "validation_error",
                "The previous upload attempt failed validation.",
            )
        if record.request_fingerprint is not None:
            await self._assert_replay_fingerprint(command=command, record=record)
        timestamp = _now(None)
        await self._idempotency.mark_in_progress(
            organization_id=tenant.organization_id,
            idempotency_key=record.idempotency_key,
            now=timestamp,
            expires_at=timestamp + self._idempotency_ttl,
        )
        await self._transaction.commit()
        await self._record_upload_event(
            AuditEventType.DOCUMENT_UPLOAD_STARTED,
            tenant=tenant,
            request_context=command.audit_context,
            now=timestamp,
            metadata={"idempotency_replay": True},
        )
        return await self._process_reserved_upload(
            command=command,
            tenant=tenant,
            key=record.idempotency_key,
        )

    async def _prepare_upload(
        self,
        command: UploadDocumentCommand,
    ) -> tuple[NormalizedUploadMetadata, StreamedUpload, str]:
        metadata = normalize_upload_metadata(
            filename=command.filename,
            declared_media_type=command.declared_media_type,
        )
        streamed = await stream_upload(command.stream, max_bytes=self._max_bytes)
        fingerprint = request_fingerprint(
            content_hash=streamed.content_hash,
            filename=metadata.filename,
            media_type=metadata.media_type,
            byte_size=streamed.byte_size,
        )
        validate_streamed_content(metadata=metadata, upload=streamed)
        streamed.body.seek(0)
        return metadata, streamed, fingerprint

    async def _assert_replay_fingerprint(
        self,
        *,
        command: UploadDocumentCommand,
        record: UploadIdempotencyRecord,
    ) -> None:
        try:
            _, streamed, fingerprint = await self._prepare_upload(command)
        except UploadValidationError as exc:
            raise IdempotencyConflictError(
                "Idempotency-Key was already used with a different upload."
            ) from exc
        finally:
            if "streamed" in locals():
                streamed.body.close()
        if record.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                "Idempotency-Key was already used with a different upload."
            )

    async def _replay_completed(
        self,
        record: UploadIdempotencyRecord,
        *,
        tenant: TenantContext,
    ) -> UploadDocumentResult:
        if record.document_id is None or record.document_version_id is None:
            raise IdempotencyConflictError("Stored idempotency result is incomplete.")
        document = await self._documents.get_document(
            organization_id=tenant.organization_id,
            document_id=record.document_id,
        )
        if document is None:
            raise IdempotencyConflictError("Stored idempotency result is unavailable.")
        version = await self._documents.get_version(
            organization_id=tenant.organization_id,
            document_id=document.id,
            version_id=record.document_version_id,
        )
        if version is None:
            raise IdempotencyConflictError("Stored idempotency result is unavailable.")
        return UploadDocumentResult(
            document=document,
            current_version=version,
            outcome=UploadDocumentOutcome.IDEMPOTENT_REPLAY,
            duplicate=record.outcome == UploadDocumentOutcome.DUPLICATE.value,
            idempotent_replay=True,
            response_status=record.response_status or 200,
        )

    async def _complete_duplicate_if_present(
        self,
        *,
        command: UploadDocumentCommand,
        tenant: TenantContext,
        idempotency_key: str,
        fingerprint: str,
        temp_key: StorageObjectKey,
        content_hash: ContentHash,
        byte_size: int,
    ) -> UploadDocumentResult | None:
        existing = await self._documents.find_document_by_tenant_content_hash(
            organization_id=tenant.organization_id,
            content_hash=content_hash,
        )
        if existing is None:
            return None
        return await self._complete_duplicate(
            command=command,
            tenant=tenant,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            temp_key=temp_key,
            duplicate=existing,
            byte_size=byte_size,
        )

    async def _complete_duplicate(
        self,
        *,
        command: UploadDocumentCommand,
        tenant: TenantContext,
        idempotency_key: str,
        fingerprint: str,
        temp_key: StorageObjectKey,
        duplicate: Document,
        byte_size: int,
    ) -> UploadDocumentResult:
        await self._delete_temp_best_effort(temp_key)
        version = await self._require_current_version(duplicate)
        await self._idempotency.complete(
            organization_id=tenant.organization_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            document_id=duplicate.id,
            document_version_id=version.id,
            response_status=200,
            outcome=UploadDocumentOutcome.DUPLICATE.value,
            now=_now(None),
        )
        await self._transaction.commit()
        await self._record_upload_event(
            AuditEventType.DOCUMENT_DUPLICATE_DETECTED,
            tenant=tenant,
            request_context=command.audit_context,
            now=_now(None),
            metadata={"document_id": duplicate.id.value, "byte_size": byte_size},
        )
        return UploadDocumentResult(
            document=duplicate,
            current_version=version,
            outcome=UploadDocumentOutcome.DUPLICATE,
            duplicate=True,
            idempotent_replay=False,
            response_status=200,
        )

    async def _promote_new_document(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        tenant: TenantContext,
        temp_key: StorageObjectKey,
        media_type: str,
        byte_size: int,
        content_hash: ContentHash,
    ) -> tuple[Document, DocumentVersion]:
        final_key = StorageObjectKey.for_document_content(
            organization_id=tenant.organization_id,
            content_hash=content_hash,
        )
        existing_object = await self._storage.head_object(final_key)
        if existing_object is None:
            await self._storage.promote_temp_object(
                PromoteObjectRequest(
                    source_key=temp_key,
                    destination_key=final_key,
                    media_type=media_type,
                )
            )
        elif existing_object.byte_size != byte_size:
            raise ObjectStorageUnavailableError("Final object metadata is inconsistent.")
        else:
            await self._delete_temp_best_effort(temp_key)
        stored_version = await self._documents.mark_version_stored(
            organization_id=tenant.organization_id,
            document_id=document.id,
            version_id=version.id,
        )
        stored_document = document.mark_stored(actor_user_id=tenant.user_id, now=_now(None))
        await self._documents.archive_document(stored_document)
        return stored_document, stored_version

    async def _mark_upload_storage_failed(
        self,
        *,
        command: UploadDocumentCommand,
        tenant: TenantContext,
        idempotency_key: str,
        fingerprint: str,
        document: Document,
        version: DocumentVersion,
    ) -> None:
        await self._documents.mark_version_failed(
            organization_id=tenant.organization_id,
            document_id=document.id,
            version_id=version.id,
        )
        failed_document = document.mark_failed(actor_user_id=tenant.user_id, now=_now(None))
        await self._documents.archive_document(failed_document)
        await self._idempotency.fail(
            organization_id=tenant.organization_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            error_code="object_storage_unavailable",
            response_status=503,
            retryable=True,
            now=_now(None),
        )
        await self._transaction.commit()
        await self._record_failed_upload(
            command,
            tenant=tenant,
            error_code="object_storage_unavailable",
            document_id=document.id.value,
        )

    async def _require_current_version(self, document: Document) -> DocumentVersion:
        version = await self._documents.get_version(
            organization_id=document.organization_id,
            document_id=document.id,
            version_id=document.current_version_id,
        )
        if version is None:
            msg = "Document current version was not found."
            raise DocumentNotFoundError(msg)
        return version

    def _new_document_pair(
        self,
        *,
        tenant: TenantContext,
        metadata: NormalizedUploadMetadata,
        content_hash: ContentHash,
        byte_size: int,
        now: datetime,
    ) -> tuple[Document, DocumentVersion]:
        document_id = DocumentId(_new_uuid(self._ids))
        version = DocumentVersion.create(
            id=DocumentVersionId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            document_id=document_id,
            version_number=1,
            original_filename=metadata.filename,
            media_type=metadata.media_type,
            byte_size=byte_size,
            content_hash=content_hash,
            storage_state=DocumentStorageState.PENDING,
            created_at=now,
            created_by_user_id=tenant.user_id,
        )
        document = Document.register(
            id=document_id,
            organization_id=tenant.organization_id,
            display_filename=metadata.filename,
            source_type=DocumentSourceType.UPLOAD,
            source_reference=None,
            current_version=version,
            created_by_user_id=tenant.user_id,
            now=now,
        )
        return document, version

    async def _delete_temp_best_effort(self, key: StorageObjectKey) -> None:
        try:
            await self._storage.delete_object(key)
        except Exception:
            return

    async def _record_failed_upload(
        self,
        command: UploadDocumentCommand,
        *,
        tenant: TenantContext,
        error_code: str,
        document_id: UUID | None = None,
    ) -> None:
        metadata: dict[str, object] = {"error_code": error_code}
        if document_id is not None:
            metadata["document_id"] = document_id
        await self._record_upload_event(
            AuditEventType.DOCUMENT_UPLOAD_FAILED,
            tenant=tenant,
            request_context=command.audit_context,
            now=_now(None),
            outcome=AuditOutcome.FAILURE,
            metadata=metadata,
        )

    async def _record_upload_event(
        self,
        event_type: AuditEventType,
        *,
        tenant: TenantContext,
        request_context: AuditRequestContext | None,
        now: datetime,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            AuditEvent.create(
                id=_new_uuid(self._ids),
                event_type=event_type,
                outcome=outcome,
                occurred_at=now,
                actor_user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                request_context=request_context,
                metadata=metadata or {},
            )
        )


def _now(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        msg = "Application timestamp must be timezone-aware."
        raise ValueError(msg)
    return timestamp.astimezone(UTC)


def _new_uuid(ids: IdGenerator | None) -> UUID:
    if ids is None:
        return uuid4()
    return ids.new_uuid()


async def _commit(transaction: TransactionManager | None) -> None:
    if transaction is not None:
        await transaction.commit()


async def _rollback(transaction: TransactionManager | None) -> None:
    if transaction is not None:
        await transaction.rollback()

"""Document application services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
)
from workflowforge_application.documents.ports import (
    DocumentListFilter,
    DocumentProjection,
    DocumentRepository,
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

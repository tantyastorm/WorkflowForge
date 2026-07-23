"""Batch application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome, AuditRequestContext
from workflowforge_domain.batches import Batch, BatchDocument, BatchDocumentId, BatchId, BatchStatus
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission

from workflowforge_application.audit import AuditRecorder
from workflowforge_application.authorization import AuthorizationPolicy, TenantContext
from workflowforge_application.documents import ConcurrencyConflictError, DocumentNotFoundError
from workflowforge_application.identity.ports import IdGenerator, TransactionManager


class BatchApplicationError(Exception):
    """Base class for batch application failures."""


class BatchNotFoundError(BatchApplicationError):
    """Raised when a batch is not found."""


class BatchDocumentConflictError(BatchApplicationError):
    """Raised when batch-document membership conflicts."""


@dataclass(frozen=True, slots=True)
class BatchListFilter:
    """Batch list filter."""

    limit: int = 25
    offset: int = 0
    status: BatchStatus | None = None
    archived: bool | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class BatchListPage:
    """Offset-paginated batches."""

    items: list[Batch]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class CreateBatchCommand:
    """Create batch command."""

    name: str
    description: str | None = None
    external_reference: str | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class UpdateBatchCommand:
    """Update batch command."""

    batch_id: BatchId
    lock_version: int
    name: str | None = None
    description: str | None = None
    external_reference: str | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class BatchDocumentCommand:
    """Batch document membership command."""

    batch_id: BatchId
    document_id: DocumentId
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class ArchiveBatchCommand:
    """Archive batch command."""

    batch_id: BatchId
    lock_version: int
    audit_context: AuditRequestContext | None = None


class BatchRepository(Protocol):
    """Batch persistence port."""

    async def add(self, batch: Batch) -> Batch:
        """Persist a batch."""

    async def get(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        """Return a tenant-scoped batch."""

    async def get_for_update(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        """Return a tenant-scoped batch with row lock."""

    async def list_batches(
        self,
        *,
        organization_id: UUID,
        query: BatchListFilter,
    ) -> BatchListPage:
        """Return a page of batches."""

    async def update(self, batch: Batch) -> Batch:
        """Persist updated batch state."""

    async def add_document(self, membership: BatchDocument) -> BatchDocument:
        """Add document membership idempotently."""

    async def remove_document(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
        document_id: DocumentId,
    ) -> bool:
        """Remove document membership."""

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        batch_id: BatchId,
    ) -> list[BatchDocument]:
        """Return batch document memberships."""


class BatchService:
    """Batch use cases."""

    def __init__(
        self,
        repository: BatchRepository,
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

    async def create(self, command: CreateBatchCommand, *, tenant: TenantContext) -> Batch:
        """Create a batch."""

        self._authorization.require(tenant, Permission.BATCH_WRITE)
        timestamp = _now()
        batch = Batch.create(
            id=BatchId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            name=command.name,
            description=command.description,
            external_reference=command.external_reference,
            created_by_user_id=tenant.user_id,
            now=timestamp,
        )
        try:
            saved = await self._repository.add(batch)
            await self._record(
                AuditEventType.BATCH_CREATED,
                tenant=tenant,
                batch=saved,
                request_context=command.audit_context,
                now=timestamp,
            )
            await _commit(self._transaction)
            return saved
        except Exception:
            await _rollback(self._transaction)
            raise

    async def get(self, batch_id: BatchId, *, tenant: TenantContext) -> Batch:
        """Get a batch."""

        self._authorization.require(tenant, Permission.BATCH_READ)
        batch = await self._repository.get(
            organization_id=tenant.organization_id,
            batch_id=batch_id,
        )
        if batch is None:
            raise BatchNotFoundError("Batch was not found.")
        return batch

    async def list_batches(
        self,
        *,
        tenant: TenantContext,
        query: BatchListFilter,
    ) -> BatchListPage:
        """List batches."""

        self._authorization.require(tenant, Permission.BATCH_READ)
        return await self._repository.list_batches(
            organization_id=tenant.organization_id,
            query=query,
        )

    async def update(self, command: UpdateBatchCommand, *, tenant: TenantContext) -> Batch:
        """Update a batch."""

        self._authorization.require(tenant, Permission.BATCH_WRITE)
        batch = await self._repository.get_for_update(
            organization_id=tenant.organization_id,
            batch_id=command.batch_id,
        )
        if batch is None:
            raise BatchNotFoundError("Batch was not found.")
        if batch.lock_version != command.lock_version:
            raise ConcurrencyConflictError("Batch was changed by another request.")
        updated = batch.update(
            name=command.name,
            description=command.description,
            external_reference=command.external_reference,
            actor_user_id=tenant.user_id,
            now=_now(),
        )
        try:
            saved = await self._repository.update(updated)
            await self._record(
                AuditEventType.BATCH_UPDATED,
                tenant=tenant,
                batch=saved,
                request_context=command.audit_context,
                now=saved.updated_at,
            )
            await _commit(self._transaction)
            return saved
        except Exception:
            await _rollback(self._transaction)
            raise

    async def add_document(
        self,
        command: BatchDocumentCommand,
        *,
        tenant: TenantContext,
    ) -> BatchDocument:
        """Add a document to a batch idempotently."""

        self._authorization.require(tenant, Permission.BATCH_MANAGE_DOCUMENTS)
        await self.get(command.batch_id, tenant=tenant)
        membership = BatchDocument(
            id=BatchDocumentId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            batch_id=command.batch_id,
            document_id=command.document_id,
            added_at=_now(),
            added_by_user_id=tenant.user_id,
        )
        try:
            saved = await self._repository.add_document(membership)
            await self._record(
                AuditEventType.BATCH_DOCUMENT_ADDED,
                tenant=tenant,
                batch_id=command.batch_id,
                request_context=command.audit_context,
                now=saved.added_at,
                metadata={"document_id": command.document_id.value},
            )
            await _commit(self._transaction)
            return saved
        except DocumentNotFoundError:
            await _rollback(self._transaction)
            raise

    async def remove_document(
        self,
        command: BatchDocumentCommand,
        *,
        tenant: TenantContext,
    ) -> bool:
        """Remove a document from a batch."""

        self._authorization.require(tenant, Permission.BATCH_MANAGE_DOCUMENTS)
        await self.get(command.batch_id, tenant=tenant)
        removed = await self._repository.remove_document(
            organization_id=tenant.organization_id,
            batch_id=command.batch_id,
            document_id=command.document_id,
        )
        await self._record(
            AuditEventType.BATCH_DOCUMENT_REMOVED,
            tenant=tenant,
            batch_id=command.batch_id,
            request_context=command.audit_context,
            now=_now(),
            metadata={"document_id": command.document_id.value, "removed": removed},
        )
        await _commit(self._transaction)
        return removed

    async def archive(self, command: ArchiveBatchCommand, *, tenant: TenantContext) -> Batch:
        """Archive a batch."""

        self._authorization.require(tenant, Permission.BATCH_ARCHIVE)
        batch = await self._repository.get_for_update(
            organization_id=tenant.organization_id,
            batch_id=command.batch_id,
        )
        if batch is None:
            raise BatchNotFoundError("Batch was not found.")
        if batch.lock_version != command.lock_version:
            raise ConcurrencyConflictError("Batch was changed by another request.")
        archived = batch.archive(actor_user_id=tenant.user_id, now=_now())
        saved = await self._repository.update(archived)
        await self._record(
            AuditEventType.BATCH_ARCHIVED,
            tenant=tenant,
            batch=saved,
            request_context=command.audit_context,
            now=saved.updated_at,
        )
        await _commit(self._transaction)
        return saved

    async def list_documents(
        self,
        batch_id: BatchId,
        *,
        tenant: TenantContext,
    ) -> list[BatchDocument]:
        """List batch document memberships."""

        await self.get(batch_id, tenant=tenant)
        return await self._repository.list_documents(
            organization_id=tenant.organization_id,
            batch_id=batch_id,
        )

    async def _record(
        self,
        event_type: AuditEventType,
        *,
        tenant: TenantContext,
        request_context: AuditRequestContext | None,
        now: datetime,
        batch: Batch | None = None,
        batch_id: BatchId | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self._audit is None:
            return
        target_id = batch.id.value if batch is not None else batch_id.value if batch_id else None
        await self._audit.record(
            AuditEvent.create(
                id=_new_uuid(self._ids),
                event_type=event_type,
                outcome=AuditOutcome.SUCCESS,
                occurred_at=now,
                actor_user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                request_context=request_context,
                metadata={"target_type": "batch", "target_id": target_id, **(metadata or {})},
            )
        )


def _now() -> datetime:
    return datetime.now(UTC)


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

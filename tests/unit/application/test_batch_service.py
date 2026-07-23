"""Batch application service tests."""

from uuid import UUID

import pytest
from workflowforge_application.authorization import TenantContext
from workflowforge_application.batches import (
    ArchiveBatchCommand,
    BatchDocumentCommand,
    BatchListFilter,
    BatchListPage,
    BatchNotFoundError,
    BatchService,
    CreateBatchCommand,
    UpdateBatchCommand,
)
from workflowforge_application.documents import ConcurrencyConflictError
from workflowforge_domain.audit import AuditEvent
from workflowforge_domain.batches import Batch, BatchDocument, BatchId
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission, Role

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP = UUID("99999999-9999-4999-8999-999999999999")
DOCUMENT_ID = DocumentId(UUID("33333333-3333-4333-8333-333333333333"))


async def test_batch_service_create_update_membership_archive_and_audit() -> None:
    repository = InMemoryBatchRepository()
    transaction = SpyTransaction()
    audit = SpyAudit()
    service = BatchService(repository, transaction=transaction, audit=audit, ids=FixedIds())

    batch = await service.create(CreateBatchCommand(name="Batch"), tenant=_tenant())
    updated = await service.update(
        UpdateBatchCommand(batch_id=batch.id, lock_version=batch.lock_version, name="Renamed"),
        tenant=_tenant(),
    )
    membership = await service.add_document(
        BatchDocumentCommand(batch_id=batch.id, document_id=DOCUMENT_ID),
        tenant=_tenant(),
    )
    listed_memberships = await service.list_documents(batch.id, tenant=_tenant())
    removed = await service.remove_document(
        BatchDocumentCommand(batch_id=batch.id, document_id=DOCUMENT_ID),
        tenant=_tenant(),
    )
    archived = await service.archive(
        ArchiveBatchCommand(batch_id=batch.id, lock_version=updated.lock_version),
        tenant=_tenant(),
    )

    assert updated.name == "Renamed"
    assert membership.document_id == DOCUMENT_ID
    assert listed_memberships == [membership]
    assert removed is True
    assert archived.archived_at is not None
    assert transaction.commits == 5
    assert len(audit.events) == 5


async def test_batch_service_enforces_tenant_and_lock_errors() -> None:
    repository = InMemoryBatchRepository()
    service = BatchService(repository)
    batch = await service.create(CreateBatchCommand(name="Batch"), tenant=_tenant())

    with pytest.raises(ConcurrencyConflictError):
        await service.update(
            UpdateBatchCommand(batch_id=batch.id, lock_version=99, name="Late"),
            tenant=_tenant(),
        )
    with pytest.raises(BatchNotFoundError):
        await service.get(batch.id, tenant=_tenant(organization_id=UUID(int=1)))
    with pytest.raises(Exception, match="Permission denied"):
        await service.list_batches(
            tenant=_tenant(permissions=[Permission.DOCUMENT_READ]),
            query=BatchListFilter(),
        )


class InMemoryBatchRepository:
    def __init__(self) -> None:
        self.batches: dict[tuple[UUID, BatchId], Batch] = {}
        self.documents: dict[tuple[UUID, BatchId, DocumentId], BatchDocument] = {}

    async def add(self, batch: Batch) -> Batch:
        self.batches[(batch.organization_id, batch.id)] = batch
        return batch

    async def get(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        return self.batches.get((organization_id, batch_id))

    async def get_for_update(self, *, organization_id: UUID, batch_id: BatchId) -> Batch | None:
        return await self.get(organization_id=organization_id, batch_id=batch_id)

    async def list_batches(self, *, organization_id: UUID, query: BatchListFilter) -> BatchListPage:
        items = [
            batch for (tenant_id, _), batch in self.batches.items() if tenant_id == organization_id
        ]
        return BatchListPage(items=items, total=len(items), limit=query.limit, offset=query.offset)

    async def update(self, batch: Batch) -> Batch:
        self.batches[(batch.organization_id, batch.id)] = batch
        return batch

    async def add_document(self, membership: BatchDocument) -> BatchDocument:
        key = (membership.organization_id, membership.batch_id, membership.document_id)
        self.documents.setdefault(key, membership)
        return self.documents[key]

    async def remove_document(
        self, *, organization_id: UUID, batch_id: BatchId, document_id: DocumentId
    ) -> bool:
        return self.documents.pop((organization_id, batch_id, document_id), None) is not None

    async def list_documents(
        self, *, organization_id: UUID, batch_id: BatchId
    ) -> list[BatchDocument]:
        return [
            membership
            for (tenant_id, current_batch_id, _), membership in self.documents.items()
            if tenant_id == organization_id and current_batch_id == batch_id
        ]


class FixedIds:
    def __init__(self) -> None:
        self.next_int = 1

    def new_uuid(self) -> UUID:
        value = UUID(int=self.next_int)
        self.next_int += 1
        return value


class SpyTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class SpyAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


def _tenant(
    *,
    organization_id: UUID = ORG,
    permissions: list[Permission] | None = None,
) -> TenantContext:
    return TenantContext.trusted_with_permissions(
        user_id=USER,
        organization_id=organization_id,
        membership_id=MEMBERSHIP,
        role=Role.OPERATOR,
        permissions=permissions
        or [
            Permission.BATCH_READ,
            Permission.BATCH_WRITE,
            Permission.BATCH_ARCHIVE,
            Permission.BATCH_MANAGE_DOCUMENTS,
        ],
    )

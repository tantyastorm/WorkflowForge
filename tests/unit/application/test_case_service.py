"""Case application service tests."""

from uuid import UUID

import pytest
from workflowforge_application.authorization import TenantContext
from workflowforge_application.cases import (
    CaseDocumentCommand,
    CaseListFilter,
    CaseListPage,
    CaseNotFoundError,
    CaseService,
    CaseStateCommand,
    CompleteCaseTaskCommand,
    CreateCaseCommand,
    CreateCaseCommentCommand,
    CreateCaseDecisionCommand,
    CreateCaseTaskCommand,
    UpdateCaseCommand,
    UpdateCaseTaskCommand,
)
from workflowforge_application.documents import ConcurrencyConflictError
from workflowforge_domain.audit import AuditEvent
from workflowforge_domain.cases import (
    Case,
    CaseComment,
    CaseDecision,
    CaseDocument,
    CaseId,
    CaseTask,
    CaseTaskId,
)
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission, Role

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP = UUID("99999999-9999-4999-8999-999999999999")
DOCUMENT_ID = DocumentId(UUID("33333333-3333-4333-8333-333333333333"))


async def test_case_service_full_casework_flow() -> None:
    repository = InMemoryCaseRepository()
    transaction = SpyTransaction()
    audit = SpyAudit()
    service = CaseService(repository, transaction=transaction, audit=audit, ids=FixedIds())

    case = await service.create(CreateCaseCommand(title="Case"), tenant=_tenant())
    updated = await service.update(
        UpdateCaseCommand(case_id=case.id, lock_version=case.lock_version, title="Renamed"),
        tenant=_tenant(),
    )
    document = await service.add_document(
        CaseDocumentCommand(case_id=case.id, document_id=DOCUMENT_ID),
        tenant=_tenant(),
    )
    comment = await service.create_comment(
        CreateCaseCommentCommand(case_id=case.id, body="Looks good"),
        tenant=_tenant(),
    )
    task = await service.create_task(
        CreateCaseTaskCommand(case_id=case.id, title="Review"),
        tenant=_tenant(),
    )
    changed_task = await service.update_task(
        UpdateCaseTaskCommand(
            case_id=case.id,
            task_id=task.id,
            lock_version=task.lock_version,
            title="Review documents",
        ),
        tenant=_tenant(),
    )
    completed_task = await service.complete_task(
        CompleteCaseTaskCommand(
            case_id=case.id,
            task_id=changed_task.id,
            lock_version=changed_task.lock_version,
        ),
        tenant=_tenant(),
    )
    decision = await service.create_decision(
        CreateCaseDecisionCommand(case_id=case.id, decision_type="accept", rationale="Complete"),
        tenant=_tenant(),
    )
    documents, comments, tasks, decisions = await service.details(case.id, tenant=_tenant())
    closed = await service.close(
        CaseStateCommand(case_id=case.id, lock_version=updated.lock_version),
        tenant=_tenant(),
    )
    reopened = await service.reopen(
        CaseStateCommand(case_id=case.id, lock_version=closed.lock_version),
        tenant=_tenant(),
    )
    archived = await service.archive(
        CaseStateCommand(case_id=case.id, lock_version=reopened.lock_version),
        tenant=_tenant(),
    )

    assert updated.title == "Renamed"
    assert document in documents
    assert comment in comments
    assert completed_task in tasks
    assert decision in decisions
    assert closed.closed_at is not None
    assert reopened.closed_at is None
    assert archived.archived_at is not None
    assert transaction.commits == 11
    assert len(audit.events) == 11


async def test_case_service_enforces_lock_and_permission_errors() -> None:
    repository = InMemoryCaseRepository()
    service = CaseService(repository)
    case = await service.create(CreateCaseCommand(title="Case"), tenant=_tenant())

    with pytest.raises(ConcurrencyConflictError):
        await service.close(
            CaseStateCommand(case_id=case.id, lock_version=99),
            tenant=_tenant(),
        )
    with pytest.raises(CaseNotFoundError):
        await service.get(case.id, tenant=_tenant(organization_id=UUID(int=1)))
    with pytest.raises(Exception, match="Permission denied"):
        await service.list_cases(
            tenant=_tenant(permissions=[Permission.DOCUMENT_READ]),
            query=CaseListFilter(),
        )


class InMemoryCaseRepository:
    def __init__(self) -> None:
        self.cases: dict[tuple[UUID, CaseId], Case] = {}
        self.documents: list[CaseDocument] = []
        self.comments: list[CaseComment] = []
        self.tasks: dict[tuple[UUID, CaseId, CaseTaskId], CaseTask] = {}
        self.decisions: list[CaseDecision] = []

    async def add(self, case: Case) -> Case:
        self.cases[(case.organization_id, case.id)] = case
        return case

    async def get(self, *, organization_id: UUID, case_id: CaseId) -> Case | None:
        return self.cases.get((organization_id, case_id))

    async def get_for_update(self, *, organization_id: UUID, case_id: CaseId) -> Case | None:
        return await self.get(organization_id=organization_id, case_id=case_id)

    async def list_cases(self, *, organization_id: UUID, query: CaseListFilter) -> CaseListPage:
        items = [
            case for (tenant_id, _), case in self.cases.items() if tenant_id == organization_id
        ]
        return CaseListPage(items=items, total=len(items), limit=query.limit, offset=query.offset)

    async def update(self, case: Case) -> Case:
        self.cases[(case.organization_id, case.id)] = case
        return case

    async def add_document(self, membership: CaseDocument) -> CaseDocument:
        self.documents.append(membership)
        return membership

    async def remove_document(
        self, *, organization_id: UUID, case_id: CaseId, document_id: DocumentId
    ) -> bool:
        before = len(self.documents)
        self.documents = [
            item
            for item in self.documents
            if not (
                item.organization_id == organization_id
                and item.case_id == case_id
                and item.document_id == document_id
            )
        ]
        return len(self.documents) != before

    async def list_documents(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseDocument]:
        return [
            item
            for item in self.documents
            if item.organization_id == organization_id and item.case_id == case_id
        ]

    async def add_comment(self, comment: CaseComment) -> CaseComment:
        self.comments.append(comment)
        return comment

    async def list_comments(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseComment]:
        return [
            item
            for item in self.comments
            if item.organization_id == organization_id and item.case_id == case_id
        ]

    async def add_task(self, task: CaseTask) -> CaseTask:
        self.tasks[(task.organization_id, task.case_id, task.id)] = task
        return task

    async def get_task_for_update(
        self, *, organization_id: UUID, case_id: CaseId, task_id: CaseTaskId
    ) -> CaseTask | None:
        return self.tasks.get((organization_id, case_id, task_id))

    async def update_task(self, task: CaseTask) -> CaseTask:
        self.tasks[(task.organization_id, task.case_id, task.id)] = task
        return task

    async def list_tasks(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseTask]:
        return [
            item
            for (tenant_id, current_case_id, _), item in self.tasks.items()
            if tenant_id == organization_id and current_case_id == case_id
        ]

    async def add_decision(self, decision: CaseDecision) -> CaseDecision:
        self.decisions.append(decision)
        return decision

    async def list_decisions(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseDecision]:
        return [
            item
            for item in self.decisions
            if item.organization_id == organization_id and item.case_id == case_id
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

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        raise AssertionError("rollback was not expected")


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
            Permission.CASE_READ,
            Permission.CASE_WRITE,
            Permission.CASE_ARCHIVE,
            Permission.CASE_MANAGE_DOCUMENTS,
            Permission.CASE_COMMENT,
            Permission.CASE_TASK,
            Permission.CASE_DECISION,
        ],
    )

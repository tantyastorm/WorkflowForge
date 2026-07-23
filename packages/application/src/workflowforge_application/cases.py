"""Case application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome, AuditRequestContext
from workflowforge_domain.cases import (
    Case,
    CaseComment,
    CaseCommentId,
    CaseDecision,
    CaseDecisionId,
    CaseDocument,
    CaseDocumentId,
    CaseId,
    CasePriority,
    CaseStatus,
    CaseTask,
    CaseTaskId,
    CaseTaskStatus,
)
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission

from workflowforge_application.audit import AuditRecorder
from workflowforge_application.authorization import AuthorizationPolicy, TenantContext
from workflowforge_application.documents import ConcurrencyConflictError
from workflowforge_application.identity.ports import IdGenerator, TransactionManager


class CaseApplicationError(Exception):
    """Base case application error."""


class CaseNotFoundError(CaseApplicationError):
    """Raised when a case is not found."""


class CaseTaskNotFoundError(CaseApplicationError):
    """Raised when a task is not found."""


@dataclass(frozen=True, slots=True)
class CaseListFilter:
    """Case list filter."""

    limit: int = 25
    offset: int = 0
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    archived: bool | None = None
    title: str | None = None


@dataclass(frozen=True, slots=True)
class CaseListPage:
    """Offset-paginated cases."""

    items: list[Case]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class CreateCaseCommand:
    title: str
    summary: str | None = None
    priority: CasePriority = CasePriority.NORMAL
    external_reference: str | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class UpdateCaseCommand:
    case_id: CaseId
    lock_version: int
    title: str | None = None
    summary: str | None = None
    priority: CasePriority | None = None
    external_reference: str | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CaseDocumentCommand:
    case_id: CaseId
    document_id: DocumentId
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CreateCaseCommentCommand:
    case_id: CaseId
    body: str
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CreateCaseTaskCommand:
    case_id: CaseId
    title: str
    description: str | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class UpdateCaseTaskCommand:
    case_id: CaseId
    task_id: CaseTaskId
    lock_version: int
    title: str | None = None
    description: str | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CompleteCaseTaskCommand:
    case_id: CaseId
    task_id: CaseTaskId
    lock_version: int
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CreateCaseDecisionCommand:
    case_id: CaseId
    decision_type: str
    rationale: str
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class CaseStateCommand:
    case_id: CaseId
    lock_version: int
    audit_context: AuditRequestContext | None = None


class CaseRepository(Protocol):
    async def add(self, case: Case) -> Case: ...
    async def get(self, *, organization_id: UUID, case_id: CaseId) -> Case | None: ...
    async def get_for_update(self, *, organization_id: UUID, case_id: CaseId) -> Case | None: ...
    async def list_cases(self, *, organization_id: UUID, query: CaseListFilter) -> CaseListPage: ...
    async def update(self, case: Case) -> Case: ...
    async def add_document(self, membership: CaseDocument) -> CaseDocument: ...
    async def remove_document(
        self, *, organization_id: UUID, case_id: CaseId, document_id: DocumentId
    ) -> bool: ...
    async def list_documents(
        self, *, organization_id: UUID, case_id: CaseId
    ) -> list[CaseDocument]: ...
    async def add_comment(self, comment: CaseComment) -> CaseComment: ...
    async def list_comments(
        self, *, organization_id: UUID, case_id: CaseId
    ) -> list[CaseComment]: ...
    async def add_task(self, task: CaseTask) -> CaseTask: ...
    async def get_task_for_update(
        self, *, organization_id: UUID, case_id: CaseId, task_id: CaseTaskId
    ) -> CaseTask | None: ...
    async def update_task(self, task: CaseTask) -> CaseTask: ...
    async def list_tasks(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseTask]: ...
    async def add_decision(self, decision: CaseDecision) -> CaseDecision: ...
    async def list_decisions(
        self, *, organization_id: UUID, case_id: CaseId
    ) -> list[CaseDecision]: ...


class CaseService:
    """Case use cases."""

    def __init__(
        self,
        repository: CaseRepository,
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

    async def create(self, command: CreateCaseCommand, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_WRITE)
        timestamp = _now()
        case = Case.create(
            id=CaseId(_new_uuid(self._ids)),
            organization_id=tenant.organization_id,
            title=command.title,
            summary=command.summary,
            priority=command.priority,
            external_reference=command.external_reference,
            created_by_user_id=tenant.user_id,
            now=timestamp,
        )
        saved = await self._repository.add(case)
        await self._record(
            AuditEventType.CASE_CREATED,
            tenant=tenant,
            case=saved,
            request_context=command.audit_context,
            now=timestamp,
        )
        await _commit(self._transaction)
        return saved

    async def get(self, case_id: CaseId, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_READ)
        case = await self._repository.get(organization_id=tenant.organization_id, case_id=case_id)
        if case is None:
            raise CaseNotFoundError("Case was not found.")
        return case

    async def list_cases(self, *, tenant: TenantContext, query: CaseListFilter) -> CaseListPage:
        self._authorization.require(tenant, Permission.CASE_READ)
        return await self._repository.list_cases(
            organization_id=tenant.organization_id, query=query
        )

    async def update(self, command: UpdateCaseCommand, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_WRITE)
        case = await self._locked_case(command.case_id, tenant, command.lock_version)
        saved = await self._repository.update(
            case.update(
                title=command.title,
                summary=command.summary,
                priority=command.priority,
                external_reference=command.external_reference,
                actor_user_id=tenant.user_id,
                now=_now(),
            )
        )
        await self._record(
            AuditEventType.CASE_UPDATED,
            tenant=tenant,
            case=saved,
            request_context=command.audit_context,
            now=saved.updated_at,
        )
        await _commit(self._transaction)
        return saved

    async def add_document(
        self, command: CaseDocumentCommand, *, tenant: TenantContext
    ) -> CaseDocument:
        self._authorization.require(tenant, Permission.CASE_MANAGE_DOCUMENTS)
        await self.get(command.case_id, tenant=tenant)
        membership = CaseDocument(
            CaseDocumentId(_new_uuid(self._ids)),
            tenant.organization_id,
            command.case_id,
            command.document_id,
            _now(),
            tenant.user_id,
        )
        saved = await self._repository.add_document(membership)
        await self._record(
            AuditEventType.CASE_DOCUMENT_ADDED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=saved.added_at,
            metadata={"document_id": command.document_id.value},
        )
        await _commit(self._transaction)
        return saved

    async def remove_document(self, command: CaseDocumentCommand, *, tenant: TenantContext) -> bool:
        self._authorization.require(tenant, Permission.CASE_MANAGE_DOCUMENTS)
        await self.get(command.case_id, tenant=tenant)
        removed = await self._repository.remove_document(
            organization_id=tenant.organization_id,
            case_id=command.case_id,
            document_id=command.document_id,
        )
        await self._record(
            AuditEventType.CASE_DOCUMENT_REMOVED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=_now(),
            metadata={"document_id": command.document_id.value, "removed": removed},
        )
        await _commit(self._transaction)
        return removed

    async def create_comment(
        self, command: CreateCaseCommentCommand, *, tenant: TenantContext
    ) -> CaseComment:
        self._authorization.require(tenant, Permission.CASE_COMMENT)
        await self.get(command.case_id, tenant=tenant)
        comment = CaseComment(
            CaseCommentId(_new_uuid(self._ids)),
            tenant.organization_id,
            command.case_id,
            command.body,
            _now(),
            tenant.user_id,
        )
        saved = await self._repository.add_comment(comment)
        await self._record(
            AuditEventType.CASE_COMMENT_CREATED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=saved.created_at,
        )
        await _commit(self._transaction)
        return saved

    async def create_task(
        self, command: CreateCaseTaskCommand, *, tenant: TenantContext
    ) -> CaseTask:
        self._authorization.require(tenant, Permission.CASE_TASK)
        await self.get(command.case_id, tenant=tenant)
        timestamp = _now()
        task = CaseTask(
            CaseTaskId(_new_uuid(self._ids)),
            tenant.organization_id,
            command.case_id,
            command.title,
            command.description,
            CaseTaskStatus.OPEN,
            command.assigned_to_user_id,
            command.due_at,
            None,
            None,
            timestamp,
            tenant.user_id,
            timestamp,
            tenant.user_id,
            1,
        )
        saved = await self._repository.add_task(task)
        await self._record(
            AuditEventType.CASE_TASK_CREATED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=timestamp,
        )
        await _commit(self._transaction)
        return saved

    async def update_task(
        self, command: UpdateCaseTaskCommand, *, tenant: TenantContext
    ) -> CaseTask:
        self._authorization.require(tenant, Permission.CASE_TASK)
        task = await self._locked_task(
            command.case_id, command.task_id, tenant, command.lock_version
        )
        saved = await self._repository.update_task(
            task.update(
                title=command.title,
                description=command.description,
                assigned_to_user_id=command.assigned_to_user_id,
                due_at=command.due_at,
                actor_user_id=tenant.user_id,
                now=_now(),
            )
        )
        await self._record(
            AuditEventType.CASE_TASK_UPDATED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=saved.updated_at,
            metadata={"task_id": saved.id.value},
        )
        await _commit(self._transaction)
        return saved

    async def complete_task(
        self, command: CompleteCaseTaskCommand, *, tenant: TenantContext
    ) -> CaseTask:
        self._authorization.require(tenant, Permission.CASE_TASK)
        task = await self._locked_task(
            command.case_id, command.task_id, tenant, command.lock_version
        )
        saved = await self._repository.update_task(
            task.complete(actor_user_id=tenant.user_id, now=_now())
        )
        await self._record(
            AuditEventType.CASE_TASK_COMPLETED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=saved.updated_at,
            metadata={"task_id": saved.id.value},
        )
        await _commit(self._transaction)
        return saved

    async def create_decision(
        self, command: CreateCaseDecisionCommand, *, tenant: TenantContext
    ) -> CaseDecision:
        self._authorization.require(tenant, Permission.CASE_DECISION)
        await self.get(command.case_id, tenant=tenant)
        decision = CaseDecision(
            CaseDecisionId(_new_uuid(self._ids)),
            tenant.organization_id,
            command.case_id,
            command.decision_type,
            command.rationale,
            _now(),
            tenant.user_id,
        )
        saved = await self._repository.add_decision(decision)
        await self._record(
            AuditEventType.CASE_DECISION_CREATED,
            tenant=tenant,
            case_id=command.case_id,
            request_context=command.audit_context,
            now=saved.created_at,
        )
        await _commit(self._transaction)
        return saved

    async def close(self, command: CaseStateCommand, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_WRITE)
        case = await self._locked_case(command.case_id, tenant, command.lock_version)
        saved = await self._repository.update(case.close(actor_user_id=tenant.user_id, now=_now()))
        await self._record(
            AuditEventType.CASE_CLOSED,
            tenant=tenant,
            case=saved,
            request_context=command.audit_context,
            now=saved.updated_at,
        )
        await _commit(self._transaction)
        return saved

    async def reopen(self, command: CaseStateCommand, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_WRITE)
        case = await self._locked_case(command.case_id, tenant, command.lock_version)
        saved = await self._repository.update(case.reopen(actor_user_id=tenant.user_id, now=_now()))
        await self._record(
            AuditEventType.CASE_REOPENED,
            tenant=tenant,
            case=saved,
            request_context=command.audit_context,
            now=saved.updated_at,
        )
        await _commit(self._transaction)
        return saved

    async def archive(self, command: CaseStateCommand, *, tenant: TenantContext) -> Case:
        self._authorization.require(tenant, Permission.CASE_ARCHIVE)
        case = await self._locked_case(command.case_id, tenant, command.lock_version)
        saved = await self._repository.update(
            case.archive(actor_user_id=tenant.user_id, now=_now())
        )
        await self._record(
            AuditEventType.CASE_ARCHIVED,
            tenant=tenant,
            case=saved,
            request_context=command.audit_context,
            now=saved.updated_at,
        )
        await _commit(self._transaction)
        return saved

    async def details(
        self, case_id: CaseId, *, tenant: TenantContext
    ) -> tuple[list[CaseDocument], list[CaseComment], list[CaseTask], list[CaseDecision]]:
        await self.get(case_id, tenant=tenant)
        return (
            await self._repository.list_documents(
                organization_id=tenant.organization_id, case_id=case_id
            ),
            await self._repository.list_comments(
                organization_id=tenant.organization_id, case_id=case_id
            ),
            await self._repository.list_tasks(
                organization_id=tenant.organization_id, case_id=case_id
            ),
            await self._repository.list_decisions(
                organization_id=tenant.organization_id, case_id=case_id
            ),
        )

    async def _locked_case(self, case_id: CaseId, tenant: TenantContext, lock_version: int) -> Case:
        case = await self._repository.get_for_update(
            organization_id=tenant.organization_id, case_id=case_id
        )
        if case is None:
            raise CaseNotFoundError("Case was not found.")
        if case.lock_version != lock_version:
            raise ConcurrencyConflictError("Case was changed by another request.")
        return case

    async def _locked_task(
        self, case_id: CaseId, task_id: CaseTaskId, tenant: TenantContext, lock_version: int
    ) -> CaseTask:
        await self.get(case_id, tenant=tenant)
        task = await self._repository.get_task_for_update(
            organization_id=tenant.organization_id, case_id=case_id, task_id=task_id
        )
        if task is None:
            raise CaseTaskNotFoundError("Case task was not found.")
        if task.lock_version != lock_version:
            raise ConcurrencyConflictError("Case task was changed by another request.")
        return task

    async def _record(
        self,
        event_type: AuditEventType,
        *,
        tenant: TenantContext,
        request_context: AuditRequestContext | None,
        now: datetime,
        case: Case | None = None,
        case_id: CaseId | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self._audit is None:
            return
        target_id = case.id.value if case is not None else case_id.value if case_id else None
        await self._audit.record(
            AuditEvent.create(
                id=_new_uuid(self._ids),
                event_type=event_type,
                outcome=AuditOutcome.SUCCESS,
                occurred_at=now,
                actor_user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                request_context=request_context,
                metadata={"target_type": "case", "target_id": target_id, **(metadata or {})},
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

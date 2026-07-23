"""Case routes."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from workflowforge_application.authorization import TenantContext
from workflowforge_application.cases import (
    CaseDocumentCommand,
    CaseListFilter,
    CaseNotFoundError,
    CaseService,
    CaseStateCommand,
    CaseTaskNotFoundError,
    CompleteCaseTaskCommand,
    CreateCaseCommand,
    CreateCaseCommentCommand,
    CreateCaseDecisionCommand,
    CreateCaseTaskCommand,
    UpdateCaseCommand,
    UpdateCaseTaskCommand,
)
from workflowforge_application.documents import ConcurrencyConflictError, DocumentNotFoundError
from workflowforge_domain.cases import (
    Case,
    CaseComment,
    CaseDecision,
    CaseDocument,
    CaseId,
    CasePriority,
    CaseStatus,
    CaseTask,
    CaseTaskId,
)
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission

from workflowforge_api.audit import audit_request_context
from workflowforge_api.dependencies import get_case_service, require_permission
from workflowforge_api.exception_handlers import ApiError
from workflowforge_api.schemas.cases import (
    CaseCommentResponse,
    CaseDecisionResponse,
    CaseDetailResponse,
    CaseDocumentRequest,
    CaseDocumentResponse,
    CaseListResponse,
    CaseResponse,
    CaseStateRequest,
    CaseTaskResponse,
    CreateCaseCommentRequest,
    CreateCaseDecisionRequest,
    CreateCaseRequest,
    CreateCaseTaskRequest,
    UpdateCaseRequest,
    UpdateCaseTaskRequest,
)

router = APIRouter(prefix="/organizations/{organization_id}/cases", tags=["cases"])


@router.get("", response_model=CaseListResponse)
async def list_cases(
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_READ))],
    service: Annotated[CaseService, Depends(get_case_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
    priority: str | None = None,
    archived: bool | None = None,
    title: str | None = None,
) -> CaseListResponse:
    page = await service.list_cases(
        tenant=tenant_context,
        query=CaseListFilter(
            limit=limit,
            offset=offset,
            status=None if status is None else _case_status(status),
            priority=None if priority is None else CasePriority(priority),
            archived=archived,
            title=title,
        ),
    )
    return CaseListResponse(
        items=[_case_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CreateCaseRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_WRITE))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    case = await service.create(
        CreateCaseCommand(
            title=body.title,
            summary=body.summary,
            priority=CasePriority(body.priority),
            external_reference=body.external_reference,
            audit_context=audit_request_context(request),
        ),
        tenant=tenant_context,
    )
    return _case_response(case)


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_READ))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseDetailResponse:
    try:
        case = await service.get(CaseId(case_id), tenant=tenant_context)
        documents, comments, tasks, decisions = await service.details(
            CaseId(case_id),
            tenant=tenant_context,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc
    return CaseDetailResponse(
        case=_case_response(case),
        documents=[_document_response(item) for item in documents],
        comments=[_comment_response(item) for item in comments],
        tasks=[_task_response(item) for item in tasks],
        decisions=[_decision_response(item) for item in decisions],
    )


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    body: UpdateCaseRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_WRITE))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    try:
        case = await service.update(
            UpdateCaseCommand(
                case_id=CaseId(case_id),
                lock_version=body.lock_version,
                title=body.title,
                summary=body.summary,
                priority=None if body.priority is None else CasePriority(body.priority),
                external_reference=body.external_reference,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict(str(exc)) from exc
    return _case_response(case)


@router.post("/{case_id}/documents", response_model=CaseDocumentResponse)
async def add_case_document(
    case_id: UUID,
    body: CaseDocumentRequest,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.CASE_MANAGE_DOCUMENTS)),
    ],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseDocumentResponse:
    try:
        membership = await service.add_document(
            CaseDocumentCommand(
                case_id=CaseId(case_id),
                document_id=DocumentId(body.document_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except (CaseNotFoundError, DocumentNotFoundError) as exc:
        raise _not_found() from exc
    return _document_response(membership)


@router.delete("/{case_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_case_document(
    case_id: UUID,
    document_id: UUID,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.CASE_MANAGE_DOCUMENTS)),
    ],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> None:
    try:
        await service.remove_document(
            CaseDocumentCommand(
                case_id=CaseId(case_id),
                document_id=DocumentId(document_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc


@router.post("/{case_id}/comments", response_model=CaseCommentResponse)
async def create_comment(
    case_id: UUID,
    body: CreateCaseCommentRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_COMMENT))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseCommentResponse:
    try:
        comment = await service.create_comment(
            CreateCaseCommentCommand(
                case_id=CaseId(case_id),
                body=body.body,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc
    return _comment_response(comment)


@router.post("/{case_id}/tasks", response_model=CaseTaskResponse)
async def create_task(
    case_id: UUID,
    body: CreateCaseTaskRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_TASK))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseTaskResponse:
    task = await service.create_task(
        CreateCaseTaskCommand(
            case_id=CaseId(case_id),
            title=body.title,
            description=body.description,
            assigned_to_user_id=body.assigned_to_user_id,
            due_at=body.due_at,
            audit_context=audit_request_context(request),
        ),
        tenant=tenant_context,
    )
    return _task_response(task)


@router.patch("/{case_id}/tasks/{task_id}", response_model=CaseTaskResponse)
async def update_task(
    case_id: UUID,
    task_id: UUID,
    body: UpdateCaseTaskRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_TASK))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseTaskResponse:
    try:
        task = await service.update_task(
            UpdateCaseTaskCommand(
                case_id=CaseId(case_id),
                task_id=CaseTaskId(task_id),
                lock_version=body.lock_version,
                title=body.title,
                description=body.description,
                assigned_to_user_id=body.assigned_to_user_id,
                due_at=body.due_at,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except (CaseNotFoundError, CaseTaskNotFoundError) as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict(str(exc)) from exc
    return _task_response(task)


@router.post("/{case_id}/tasks/{task_id}/complete", response_model=CaseTaskResponse)
async def complete_task(
    case_id: UUID,
    task_id: UUID,
    body: CaseStateRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_TASK))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseTaskResponse:
    try:
        task = await service.complete_task(
            CompleteCaseTaskCommand(
                case_id=CaseId(case_id),
                task_id=CaseTaskId(task_id),
                lock_version=body.lock_version,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except (CaseNotFoundError, CaseTaskNotFoundError) as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict(str(exc)) from exc
    return _task_response(task)


@router.post("/{case_id}/decisions", response_model=CaseDecisionResponse)
async def create_decision(
    case_id: UUID,
    body: CreateCaseDecisionRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_DECISION))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseDecisionResponse:
    decision = await service.create_decision(
        CreateCaseDecisionCommand(
            case_id=CaseId(case_id),
            decision_type=body.decision_type,
            rationale=body.rationale,
            audit_context=audit_request_context(request),
        ),
        tenant=tenant_context,
    )
    return _decision_response(decision)


@router.post("/{case_id}/close", response_model=CaseResponse)
async def close_case(
    case_id: UUID,
    body: CaseStateRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_WRITE))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    return await _state_response(service.close, case_id, body, request, tenant_context)


@router.post("/{case_id}/reopen", response_model=CaseResponse)
async def reopen_case(
    case_id: UUID,
    body: CaseStateRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_WRITE))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    return await _state_response(service.reopen, case_id, body, request, tenant_context)


@router.post("/{case_id}/archive", response_model=CaseResponse)
async def archive_case(
    case_id: UUID,
    body: CaseStateRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.CASE_ARCHIVE))],
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    return await _state_response(service.archive, case_id, body, request, tenant_context)


async def _state_response(
    method: Callable[..., Awaitable[Case]],
    case_id: UUID,
    body: CaseStateRequest,
    request: Request,
    tenant: TenantContext,
) -> CaseResponse:
    try:
        case = await method(
            CaseStateCommand(
                case_id=CaseId(case_id),
                lock_version=body.lock_version,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant,
        )
    except CaseNotFoundError as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict(str(exc)) from exc
    return _case_response(case)


def _case_response(case: Case) -> CaseResponse:
    return CaseResponse(
        id=case.id.value,
        organization_id=case.organization_id,
        title=case.title,
        summary=case.summary,
        status=case.status.value,
        priority=case.priority.value,
        external_reference=case.external_reference,
        created_at=case.created_at,
        updated_at=case.updated_at,
        closed_at=case.closed_at,
        archived_at=case.archived_at,
        lock_version=case.lock_version,
    )


def _document_response(membership: CaseDocument) -> CaseDocumentResponse:
    return CaseDocumentResponse(
        id=membership.id.value,
        case_id=membership.case_id.value,
        document_id=membership.document_id.value,
        added_at=membership.added_at,
        added_by_user_id=membership.added_by_user_id,
    )


def _comment_response(comment: CaseComment) -> CaseCommentResponse:
    return CaseCommentResponse(
        id=comment.id.value,
        case_id=comment.case_id.value,
        body=comment.body,
        created_at=comment.created_at,
        created_by_user_id=comment.created_by_user_id,
    )


def _task_response(task: CaseTask) -> CaseTaskResponse:
    return CaseTaskResponse(
        id=task.id.value,
        case_id=task.case_id.value,
        title=task.title,
        description=task.description,
        status=task.status.value,
        assigned_to_user_id=task.assigned_to_user_id,
        due_at=task.due_at,
        completed_at=task.completed_at,
        lock_version=task.lock_version,
    )


def _decision_response(decision: CaseDecision) -> CaseDecisionResponse:
    return CaseDecisionResponse(
        id=decision.id.value,
        case_id=decision.case_id.value,
        decision_type=decision.decision_type,
        rationale=decision.rationale,
        created_at=decision.created_at,
        created_by_user_id=decision.created_by_user_id,
    )


def _case_status(value: str) -> CaseStatus:
    return CaseStatus(value)


def _not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource was not found.",
    )


def _conflict(message: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="concurrency_conflict",
        message=message,
    )

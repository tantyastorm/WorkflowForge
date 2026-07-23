"""Batch routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from workflowforge_application.authorization import TenantContext
from workflowforge_application.batches import (
    ArchiveBatchCommand,
    BatchDocumentCommand,
    BatchListFilter,
    BatchNotFoundError,
    BatchService,
    CreateBatchCommand,
    UpdateBatchCommand,
)
from workflowforge_application.documents import ConcurrencyConflictError, DocumentNotFoundError
from workflowforge_domain.batches import Batch, BatchDocument, BatchId, BatchStatus
from workflowforge_domain.documents import DocumentId
from workflowforge_domain.identity import Permission

from workflowforge_api.audit import audit_request_context
from workflowforge_api.dependencies import get_batch_service, require_permission
from workflowforge_api.exception_handlers import ApiError
from workflowforge_api.schemas.batches import (
    ArchiveBatchRequest,
    BatchDocumentRequest,
    BatchDocumentResponse,
    BatchDocumentsResponse,
    BatchListResponse,
    BatchResponse,
    CreateBatchRequest,
    UpdateBatchRequest,
)

router = APIRouter(prefix="/organizations/{organization_id}/batches", tags=["batches"])


@router.get("", response_model=BatchListResponse)
async def list_batches(
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_READ))],
    service: Annotated[BatchService, Depends(get_batch_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[BatchStatus | None, Query(alias="status")] = None,
    archived: bool | None = None,
    name: str | None = None,
) -> BatchListResponse:
    """List tenant batches."""

    page = await service.list_batches(
        tenant=tenant_context,
        query=BatchListFilter(
            limit=limit,
            offset=offset,
            status=status_filter,
            archived=archived,
            name=name,
        ),
    )
    return BatchListResponse(
        items=[_batch_response(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    body: CreateBatchRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_WRITE))],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchResponse:
    """Create a tenant batch."""

    batch = await service.create(
        CreateBatchCommand(
            name=body.name,
            description=body.description,
            external_reference=body.external_reference,
            audit_context=audit_request_context(request),
        ),
        tenant=tenant_context,
    )
    return _batch_response(batch)


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_READ))],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchResponse:
    """Get a tenant batch."""

    try:
        return _batch_response(await service.get(BatchId(batch_id), tenant=tenant_context))
    except BatchNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: UUID,
    body: UpdateBatchRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_WRITE))],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchResponse:
    """Update a tenant batch."""

    try:
        batch = await service.update(
            UpdateBatchCommand(
                batch_id=BatchId(batch_id),
                lock_version=body.lock_version,
                name=body.name,
                description=body.description,
                external_reference=body.external_reference,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except BatchNotFoundError as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict("concurrency_conflict", str(exc)) from exc
    return _batch_response(batch)


@router.post("/{batch_id}/documents", response_model=BatchDocumentResponse)
async def add_batch_document(
    batch_id: UUID,
    body: BatchDocumentRequest,
    request: Request,
    response: Response,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.BATCH_MANAGE_DOCUMENTS)),
    ],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchDocumentResponse:
    """Add a document to a batch idempotently."""

    try:
        membership = await service.add_document(
            BatchDocumentCommand(
                batch_id=BatchId(batch_id),
                document_id=DocumentId(body.document_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except (BatchNotFoundError, DocumentNotFoundError) as exc:
        raise _not_found() from exc
    response.status_code = status.HTTP_200_OK
    return _membership_response(membership)


@router.delete("/{batch_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_batch_document(
    batch_id: UUID,
    document_id: UUID,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.BATCH_MANAGE_DOCUMENTS)),
    ],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> None:
    """Remove a document from a batch."""

    try:
        await service.remove_document(
            BatchDocumentCommand(
                batch_id=BatchId(batch_id),
                document_id=DocumentId(document_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except BatchNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{batch_id}/documents", response_model=BatchDocumentsResponse)
async def list_batch_documents(
    batch_id: UUID,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_READ))],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchDocumentsResponse:
    """List document memberships for a batch."""

    try:
        memberships = await service.list_documents(BatchId(batch_id), tenant=tenant_context)
    except BatchNotFoundError as exc:
        raise _not_found() from exc
    return BatchDocumentsResponse(items=[_membership_response(item) for item in memberships])


@router.post("/{batch_id}/archive", response_model=BatchResponse)
async def archive_batch(
    batch_id: UUID,
    body: ArchiveBatchRequest,
    request: Request,
    tenant_context: Annotated[TenantContext, Depends(require_permission(Permission.BATCH_ARCHIVE))],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchResponse:
    """Archive a tenant batch."""

    try:
        batch = await service.archive(
            ArchiveBatchCommand(
                batch_id=BatchId(batch_id),
                lock_version=body.lock_version,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except BatchNotFoundError as exc:
        raise _not_found() from exc
    except ConcurrencyConflictError as exc:
        raise _conflict("concurrency_conflict", str(exc)) from exc
    return _batch_response(batch)


def _batch_response(batch: Batch) -> BatchResponse:
    return BatchResponse(
        id=batch.id.value,
        organization_id=batch.organization_id,
        name=batch.name,
        description=batch.description,
        status=batch.status.value,
        external_reference=batch.external_reference,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        archived_at=batch.archived_at,
        lock_version=batch.lock_version,
    )


def _membership_response(membership: BatchDocument) -> BatchDocumentResponse:
    return BatchDocumentResponse(
        id=membership.id.value,
        batch_id=membership.batch_id.value,
        document_id=membership.document_id.value,
        added_at=membership.added_at,
        added_by_user_id=membership.added_by_user_id,
    )


def _not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource was not found.",
    )


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status_code=status.HTTP_409_CONFLICT, code=code, message=message)

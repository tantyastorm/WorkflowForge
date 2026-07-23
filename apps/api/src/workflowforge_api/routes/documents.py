"""Document upload routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status
from workflowforge_application.authorization import TenantContext
from workflowforge_application.documents import (
    ConcurrencyConflictError,
    DocumentArchiveCommand,
    DocumentDownloadCommand,
    DocumentDownloadResult,
    DocumentService,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
    ObjectStorage,
    ObjectStorageUnavailableError,
    UploadDocument,
    UploadDocumentCommand,
    UploadDocumentResult,
    UploadValidationError,
)
from workflowforge_domain.documents import (
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentId,
    DocumentSourceType,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionId,
)
from workflowforge_domain.identity import Permission

from workflowforge_api.audit import audit_request_context
from workflowforge_api.dependencies import (
    get_document_service,
    get_object_storage,
    get_upload_document,
    require_permission,
)
from workflowforge_api.exception_handlers import ApiError
from workflowforge_api.schemas.documents import (
    ArchiveDocumentRequest,
    DocumentArtifactResponse,
    DocumentArtifactsResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentSummaryResponse,
    DocumentVersionResponse,
    DocumentVersionsResponse,
    DownloadUrlResponse,
    UploadDocumentResponse,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["documents"],
)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List tenant documents",
)
async def list_documents(
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    archived: bool | None = None,
    source_type: DocumentSourceType | None = None,
    media_type: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    filename: str | None = None,
) -> DocumentListResponse:
    """Return paginated safe document metadata."""

    from datetime import datetime

    from workflowforge_application.documents import DocumentListFilter

    page = await service.list_documents(
        tenant=tenant_context,
        query=DocumentListFilter(
            limit=limit,
            offset=offset,
            status=status_filter,
            archived=archived,
            source_type=source_type,
            media_type=media_type,
            created_from=datetime.fromisoformat(created_from) if created_from else None,
            created_to=datetime.fromisoformat(created_to) if created_to else None,
            filename=filename,
        ),
    )
    return DocumentListResponse(
        items=[
            DocumentSummaryResponse(
                id=item.id.value,
                organization_id=item.organization_id,
                display_filename=item.display_filename,
                source_type=item.source_type.value,
                status=item.status.value,
                current_version_id=item.current_version_id.value,
                media_type=item.media_type,
                byte_size=item.byte_size,
                storage_state=item.storage_state,
                created_at=item.created_at,
                updated_at=item.updated_at,
                lock_version=item.lock_version,
            )
            for item in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a tenant document",
    responses={
        200: {"description": "Duplicate upload or idempotent replay."},
        401: {"description": "Authentication is required."},
        403: {"description": "Tenant access or permission is denied."},
        409: {"description": "Idempotency conflict or upload already in progress."},
        422: {"description": "Upload metadata or content validation failed."},
        503: {"description": "Object storage is unavailable."},
    },
)
async def upload_document(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="Document file to upload.")],
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_WRITE)),
    ],
    upload: Annotated[UploadDocument, Depends(get_upload_document)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> UploadDocumentResponse:
    """Upload a document object and tenant-scoped metadata."""

    if idempotency_key is None:
        await file.close()
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_idempotency_key",
            message="Idempotency-Key header is required.",
        )
    try:
        result = await upload(
            UploadDocumentCommand(
                filename=file.filename,
                declared_media_type=file.content_type,
                stream=file,
                idempotency_key=idempotency_key,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except InvalidIdempotencyKeyError as exc:
        raise _upload_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, str(exc)) from exc
    except UploadValidationError as exc:
        raise _upload_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise _upload_error(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
    except IdempotencyInProgressError as exc:
        raise _upload_error(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
    except ObjectStorageUnavailableError as exc:
        raise _upload_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "object_storage_unavailable",
            str(exc),
        ) from exc
    finally:
        await file.close()
    response.status_code = result.response_status
    if result.idempotent_replay:
        response.headers["Idempotency-Replayed"] = "true"
    return _response_from_result(result)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentDetailResponse:
    """Return one tenant-scoped document."""

    document = await _get_document_or_404(service, document_id, tenant=tenant_context)
    version = await service.get_version(
        tenant=tenant_context,
        document_id=document.id,
        version_id=document.current_version_id,
    )
    return DocumentDetailResponse(
        document=_document_response(document),
        current_version=_version_response(version),
    )


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: UUID,
    body: ArchiveDocumentRequest,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_ARCHIVE)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    """Archive one tenant-scoped document."""

    try:
        document = await service.archive_document_with_lock(
            DocumentArchiveCommand(
                document_id=DocumentId(document_id),
                expected_lock_version=body.lock_version,
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
        )
    except ConcurrencyConflictError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="concurrency_conflict",
            message=str(exc),
        ) from exc
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise
    return _document_response(document)


@router.get("/{document_id}/versions", response_model=DocumentVersionsResponse)
async def list_versions(
    document_id: UUID,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_VERSION_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentVersionsResponse:
    """Return safe version metadata for one document."""

    try:
        versions = await service.list_versions(DocumentId(document_id), tenant=tenant_context)
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise
    return DocumentVersionsResponse(items=[_version_response(version) for version in versions])


@router.get(
    "/{document_id}/versions/{version_id}",
    response_model=DocumentVersionResponse,
)
async def get_version(
    document_id: UUID,
    version_id: UUID,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_VERSION_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentVersionResponse:
    """Return one safe document version."""

    try:
        version = await service.get_version(
            tenant=tenant_context,
            document_id=DocumentId(document_id),
            version_id=DocumentVersionId(version_id),
        )
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise
    return _version_response(version)


@router.get("/{document_id}/artifacts", response_model=DocumentArtifactsResponse)
async def list_artifacts(
    document_id: UUID,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.ARTIFACT_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentArtifactsResponse:
    """Return safe artifact metadata for one document."""

    try:
        artifacts = await service.list_artifacts(DocumentId(document_id), tenant=tenant_context)
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise
    return DocumentArtifactsResponse(items=[_artifact_response(artifact) for artifact in artifacts])


@router.get("/{document_id}/artifacts/{artifact_id}", response_model=DocumentArtifactResponse)
async def get_artifact(
    document_id: UUID,
    artifact_id: UUID,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.ARTIFACT_READ)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentArtifactResponse:
    """Return one safe artifact metadata response."""

    try:
        artifact = await service.get_artifact(
            tenant=tenant_context,
            document_id=DocumentId(document_id),
            artifact_id=DocumentArtifactId(artifact_id),
        )
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise
    return _artifact_response(artifact)


@router.get("/{document_id}/download", response_model=DownloadUrlResponse)
async def download_document(
    document_id: UUID,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_DOWNLOAD)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
    storage_adapter: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> DownloadUrlResponse:
    """Create a short-lived signed URL for the current version."""

    return await _download_response(
        await service.create_download_url(
            DocumentDownloadCommand(
                document_id=DocumentId(document_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
            storage=storage_adapter,
        )
    )


@router.get(
    "/{document_id}/versions/{version_id}/download",
    response_model=DownloadUrlResponse,
)
async def download_version(
    document_id: UUID,
    version_id: UUID,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.DOCUMENT_DOWNLOAD)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
    storage_adapter: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> DownloadUrlResponse:
    """Create a short-lived signed URL for a version."""

    return await _download_response(
        await service.create_download_url(
            DocumentDownloadCommand(
                document_id=DocumentId(document_id),
                version_id=DocumentVersionId(version_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
            storage=storage_adapter,
        )
    )


@router.get(
    "/{document_id}/artifacts/{artifact_id}/download",
    response_model=DownloadUrlResponse,
)
async def download_artifact(
    document_id: UUID,
    artifact_id: UUID,
    request: Request,
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.ARTIFACT_DOWNLOAD)),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
    storage_adapter: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> DownloadUrlResponse:
    """Create a short-lived signed URL for an artifact."""

    return await _download_response(
        await service.create_download_url(
            DocumentDownloadCommand(
                document_id=DocumentId(document_id),
                artifact_id=DocumentArtifactId(artifact_id),
                audit_context=audit_request_context(request),
            ),
            tenant=tenant_context,
            storage=storage_adapter,
        )
    )


def _upload_error(status_code: int, code: str, message: str) -> ApiError:
    return ApiError(status_code=status_code, code=code, message=message)


def _response_from_result(result: UploadDocumentResult) -> UploadDocumentResponse:
    return UploadDocumentResponse(
        document=_document_response(result.document),
        current_version=_version_response(result.current_version),
        outcome=result.outcome.value,
        duplicate=result.duplicate,
        idempotent_replay=result.idempotent_replay,
    )


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id.value,
        organization_id=document.organization_id,
        display_filename=document.display_filename,
        source_type=document.source_type.value,
        status=document.status.value,
        current_version_id=document.current_version_id.value,
        created_at=document.created_at,
        updated_at=document.updated_at,
        lock_version=document.lock_version,
    )


def _version_response(version: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        id=version.id.value,
        document_id=version.document_id.value,
        version_number=version.version_number,
        original_filename=version.original_filename,
        media_type=version.media_type,
        byte_size=version.byte_size,
        content_hash=version.content_hash.value,
        storage_state=version.storage_state.value,
        created_at=version.created_at,
    )


def _artifact_response(artifact: DocumentArtifact) -> DocumentArtifactResponse:
    return DocumentArtifactResponse(
        id=artifact.id.value,
        document_id=artifact.document_id.value,
        document_version_id=(
            artifact.document_version_id.value if artifact.document_version_id is not None else None
        ),
        artifact_type=artifact.artifact_type.value,
        media_type=artifact.media_type,
        byte_size=artifact.byte_size,
        content_hash=artifact.content_hash.value if artifact.content_hash is not None else None,
        metadata=dict(artifact.metadata),
        created_at=artifact.created_at,
    )


async def _get_document_or_404(
    service: DocumentService,
    document_id: UUID,
    *,
    tenant: TenantContext,
) -> Document:
    try:
        return await service.get_document(DocumentId(document_id), tenant=tenant)
    except Exception as exc:
        if exc.__class__.__name__ == "DocumentNotFoundError":
            raise _not_found() from exc
        raise


async def _download_response(result: DocumentDownloadResult) -> DownloadUrlResponse:
    return DownloadUrlResponse(
        url=result.url,
        expires_at=result.expires_at,
        filename=result.filename,
        media_type=result.media_type,
        byte_size=result.byte_size,
    )


def _not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="resource_not_found",
        message="The requested resource was not found.",
    )

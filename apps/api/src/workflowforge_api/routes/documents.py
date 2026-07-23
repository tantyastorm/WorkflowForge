"""Document upload routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Request, Response, UploadFile, status
from workflowforge_application.authorization import TenantContext
from workflowforge_application.documents import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
    ObjectStorageUnavailableError,
    UploadDocument,
    UploadDocumentCommand,
    UploadDocumentResult,
    UploadValidationError,
)
from workflowforge_domain.documents import Document, DocumentVersion
from workflowforge_domain.identity import Permission

from workflowforge_api.audit import audit_request_context
from workflowforge_api.dependencies import get_upload_document, require_permission
from workflowforge_api.exception_handlers import ApiError
from workflowforge_api.schemas.documents import (
    DocumentResponse,
    DocumentVersionResponse,
    UploadDocumentResponse,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/documents",
    tags=["documents"],
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

"""Document API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentVersionResponse(BaseModel):
    """Safe current-version metadata for upload responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    version_number: int
    original_filename: str
    media_type: str
    byte_size: int
    content_hash: str
    storage_state: str
    created_at: datetime


class DocumentArtifactResponse(BaseModel):
    """Safe artifact metadata."""

    id: UUID
    document_id: UUID
    document_version_id: UUID | None
    artifact_type: str
    media_type: str
    byte_size: int
    content_hash: str | None
    metadata: dict[str, object]
    created_at: datetime


class DocumentResponse(BaseModel):
    """Safe document metadata for upload responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    display_filename: str
    source_type: str
    status: str
    current_version_id: UUID
    created_at: datetime
    updated_at: datetime
    lock_version: int


class DocumentSummaryResponse(DocumentResponse):
    """Document list item with current version summary."""

    media_type: str
    byte_size: int
    storage_state: str


class DocumentDetailResponse(BaseModel):
    """Document details response."""

    document: DocumentResponse
    current_version: DocumentVersionResponse


class DocumentListResponse(BaseModel):
    """Offset-paginated documents response."""

    items: list[DocumentSummaryResponse]
    total: int
    limit: int
    offset: int


class DocumentVersionsResponse(BaseModel):
    """Document versions response."""

    items: list[DocumentVersionResponse]


class DocumentArtifactsResponse(BaseModel):
    """Document artifacts response."""

    items: list[DocumentArtifactResponse]


class ArchiveDocumentRequest(BaseModel):
    """Archive document request."""

    lock_version: int


class DownloadUrlResponse(BaseModel):
    """Short-lived signed download URL response."""

    url: str
    expires_at: datetime
    filename: str
    media_type: str
    byte_size: int


class UploadDocumentResponse(BaseModel):
    """Document upload response."""

    document: DocumentResponse
    current_version: DocumentVersionResponse
    outcome: str
    duplicate: bool
    idempotent_replay: bool

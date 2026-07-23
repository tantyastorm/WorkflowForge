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


class UploadDocumentResponse(BaseModel):
    """Document upload response."""

    document: DocumentResponse
    current_version: DocumentVersionResponse
    outcome: str
    duplicate: bool
    idempotent_replay: bool

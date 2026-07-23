"""Batch API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BatchResponse(BaseModel):
    """Safe batch response."""

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    status: str
    external_reference: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    lock_version: int


class BatchListResponse(BaseModel):
    """Paginated batch list."""

    items: list[BatchResponse]
    total: int
    limit: int
    offset: int


class CreateBatchRequest(BaseModel):
    """Create batch request."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    external_reference: str | None = Field(default=None, max_length=255)


class UpdateBatchRequest(BaseModel):
    """Update batch request."""

    lock_version: int
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    external_reference: str | None = Field(default=None, max_length=255)


class ArchiveBatchRequest(BaseModel):
    """Archive batch request."""

    lock_version: int


class BatchDocumentRequest(BaseModel):
    """Add batch document request."""

    document_id: UUID


class BatchDocumentResponse(BaseModel):
    """Batch document membership response."""

    id: UUID
    batch_id: UUID
    document_id: UUID
    added_at: datetime
    added_by_user_id: UUID


class BatchDocumentsResponse(BaseModel):
    """Batch document memberships response."""

    items: list[BatchDocumentResponse]

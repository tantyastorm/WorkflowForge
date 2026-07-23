"""Document application ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import BinaryIO, Protocol
from uuid import UUID

from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentId,
    DocumentSourceType,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
)


@dataclass(frozen=True, slots=True)
class DocumentListFilter:
    """Tenant-scoped list query parameters."""

    limit: int = 50
    offset: int = 0
    status: DocumentStatus | None = None
    include_archived: bool = False
    source_type: DocumentSourceType | None = None


@dataclass(frozen=True, slots=True)
class DocumentProjection:
    """Read projection for document list pages."""

    id: DocumentId
    organization_id: UUID
    display_filename: str
    source_type: DocumentSourceType
    status: DocumentStatus
    current_version_id: DocumentVersionId
    created_at: datetime
    updated_at: datetime
    lock_version: int


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    """Application-safe object metadata."""

    key: StorageObjectKey
    byte_size: int
    etag: str | None = None
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class PutTempObjectRequest:
    """Request to write a temporary object."""

    key: StorageObjectKey
    body: BinaryIO
    media_type: str


@dataclass(frozen=True, slots=True)
class PromoteObjectRequest:
    """Request to promote a temporary object to a final key."""

    source_key: StorageObjectKey
    destination_key: StorageObjectKey
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadUrl:
    """Bounded signed-download URL result."""

    url: str
    expires_at: datetime


class UploadIdempotencyStatus(StrEnum):
    """Durable upload idempotency state."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UploadIdempotencyRecord:
    """Tenant-scoped upload idempotency record."""

    organization_id: UUID
    idempotency_key: str
    request_fingerprint: str | None
    status: UploadIdempotencyStatus
    document_id: DocumentId | None
    document_version_id: DocumentVersionId | None
    response_status: int | None
    outcome: str | None
    error_code: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class DocumentRepository(Protocol):
    """Tenant-aware persistence port for document metadata."""

    async def add_document(self, document: Document, version: DocumentVersion) -> Document:
        """Persist a document and its initial version metadata."""

    async def get_document(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> Document | None:
        """Return a tenant-scoped document by ID, when present."""

    async def get_document_for_update(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> Document | None:
        """Return a tenant-scoped document with a row lock, when present."""

    async def find_document_by_tenant_content_hash(
        self,
        *,
        organization_id: UUID,
        content_hash: ContentHash,
    ) -> Document | None:
        """Return the tenant document that owns the exact bytes, when present."""

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        query: DocumentListFilter,
    ) -> list[DocumentProjection]:
        """Return tenant-scoped document projections."""

    async def archive_document(self, document: Document) -> Document:
        """Persist document archive state."""

    async def add_version(self, version: DocumentVersion) -> DocumentVersion:
        """Persist a document version."""

    async def get_version(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion | None:
        """Return a tenant-scoped version by ID, when present."""

    async def list_versions(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> list[DocumentVersion]:
        """Return versions for a tenant-scoped document."""

    async def set_current_version(
        self,
        *,
        document: Document,
        version: DocumentVersion,
    ) -> Document:
        """Persist a new current-version reference on a document."""

    async def add_artifact(self, artifact: DocumentArtifact) -> DocumentArtifact:
        """Persist metadata for a real stored artifact."""

    async def get_artifact(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        artifact_id: DocumentArtifactId,
    ) -> DocumentArtifact | None:
        """Return a tenant-scoped artifact by ID, when present."""

    async def mark_version_stored(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        """Mark a version's storage state as stored."""

    async def mark_version_failed(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        """Mark a version's storage state as failed."""


class UploadIdempotencyRepository(Protocol):
    """Tenant-aware upload idempotency persistence port."""

    async def reserve(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        now: datetime,
        expires_at: datetime,
    ) -> UploadIdempotencyRecord:
        """Reserve a tenant-scoped idempotency key or return the existing record."""

    async def mark_in_progress(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        now: datetime,
        expires_at: datetime,
    ) -> UploadIdempotencyRecord:
        """Mark a retryable failed idempotency record as in-progress."""

    async def get(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
    ) -> UploadIdempotencyRecord | None:
        """Return a tenant-scoped idempotency record."""

    async def finalize_fingerprint(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist the final request fingerprint."""

    async def complete(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        document_id: DocumentId,
        document_version_id: DocumentVersionId,
        response_status: int,
        outcome: str,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist a completed idempotent response."""

    async def fail(
        self,
        *,
        organization_id: UUID,
        idempotency_key: str,
        request_fingerprint: str | None,
        error_code: str,
        response_status: int,
        retryable: bool,
        now: datetime,
    ) -> UploadIdempotencyRecord:
        """Persist a failed idempotent response."""


class ObjectStorage(Protocol):
    """Application-facing object storage port."""

    async def put_temp_stream(self, request: PutTempObjectRequest) -> StoredObjectMetadata:
        """Write a temporary object."""

    async def promote_temp_object(self, request: PromoteObjectRequest) -> StoredObjectMetadata:
        """Copy a temporary object to a final key and delete the temporary key."""

    async def head_object(self, key: StorageObjectKey) -> StoredObjectMetadata | None:
        """Return object metadata when the key exists."""

    async def delete_object(self, key: StorageObjectKey) -> None:
        """Delete an object key idempotently."""

    async def create_download_url(
        self,
        *,
        key: StorageObjectKey,
        expires_in_seconds: int,
        now: datetime,
    ) -> DownloadUrl:
        """Create a bounded download URL without exposing storage credentials."""

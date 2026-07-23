"""Document application ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

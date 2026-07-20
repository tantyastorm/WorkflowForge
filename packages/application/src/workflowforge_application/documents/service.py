"""Document application services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    StorageObjectKey,
)

from workflowforge_application.documents.errors import (
    DocumentNotFoundError,
    DuplicateDocumentContentError,
)
from workflowforge_application.documents.ports import DocumentRepository


@dataclass(frozen=True, slots=True)
class DocumentRegistrationCommand:
    """Input for registering document metadata."""

    original_filename: str
    media_type: str
    byte_size: int
    content_hash: str


class DocumentService:
    """Use cases for document metadata."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def register_document(
        self,
        command: DocumentRegistrationCommand,
        *,
        now: datetime | None = None,
    ) -> Document:
        """Register document metadata idempotently by content hash.

        Phase 2 has no tenant model yet, so content hashes are unique across the
        current repository. Re-registering the same content returns the existing
        document. The database still enforces the unique hash so concurrent
        duplicate inserts converge to the same document.
        """

        content_hash = ContentHash(command.content_hash)
        existing = await self._repository.get_by_content_hash(content_hash)
        if existing is not None:
            return existing

        document = Document.register(
            id=DocumentId.new(),
            original_filename=command.original_filename,
            media_type=command.media_type,
            byte_size=command.byte_size,
            content_hash=content_hash,
            storage_object_key=StorageObjectKey.from_content_hash(content_hash),
            now=now,
        )

        try:
            return await self._repository.add(document)
        except DuplicateDocumentContentError:
            duplicate = await self._repository.get_by_content_hash(content_hash)
            if duplicate is not None:
                return duplicate
            raise

    async def get_document(self, document_id: DocumentId) -> Document:
        """Return a document by ID or raise a sanitized not-found error."""

        document = await self._repository.get_by_id(document_id)
        if document is None:
            msg = "Document was not found."
            raise DocumentNotFoundError(msg)
        return document

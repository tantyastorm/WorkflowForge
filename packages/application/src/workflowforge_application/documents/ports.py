"""Document application ports."""

from typing import Protocol

from workflowforge_domain.documents import ContentHash, Document, DocumentId


class DocumentRepository(Protocol):
    """Persistence port for document metadata."""

    async def add(self, document: Document) -> Document:
        """Persist document metadata."""

    async def get_by_id(self, document_id: DocumentId) -> Document | None:
        """Return a document by ID, when present."""

    async def get_by_content_hash(self, content_hash: ContentHash) -> Document | None:
        """Return a document by deterministic content hash, when present."""

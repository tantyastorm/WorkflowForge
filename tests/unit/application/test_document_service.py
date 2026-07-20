"""Document application service tests."""

from datetime import UTC, datetime

import pytest
from workflowforge_application.documents import (
    DocumentNotFoundError,
    DocumentRegistrationCommand,
    DocumentService,
    DuplicateDocumentContentError,
)
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    DocumentStatus,
    StorageObjectKey,
)

HASH = "b" * 64


async def test_register_document_persists_metadata() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)

    document = await service.register_document(_command(), now=_now())

    assert document.original_filename == "example.pdf"
    assert document.media_type == "application/pdf"
    assert document.byte_size == 123
    assert document.content_hash == ContentHash(HASH)
    assert document.storage_object_key.value == f"documents/sha256/bb/bb/{HASH}"
    assert repository.added == [document]


async def test_register_document_returns_existing_document_for_duplicate_hash() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    first = await service.register_document(_command(original_filename="first.pdf"), now=_now())

    second = await service.register_document(_command(original_filename="second.pdf"), now=_now())

    assert second == first
    assert len(repository.added) == 1


async def test_register_document_handles_concurrent_duplicate_insert() -> None:
    repository = InMemoryDocumentRepository(raise_duplicate_on_add=True)
    existing = _document()
    repository.by_hash[existing.content_hash] = existing
    service = DocumentService(repository)

    document = await service.register_document(_command(), now=_now())

    assert document == existing


async def test_register_document_propagates_unresolvable_duplicate() -> None:
    repository = InMemoryDocumentRepository(raise_duplicate_on_add=True)
    service = DocumentService(repository)

    with pytest.raises(DuplicateDocumentContentError):
        await service.register_document(_command(), now=_now())


async def test_get_document_returns_document_by_id() -> None:
    repository = InMemoryDocumentRepository()
    document = await DocumentService(repository).register_document(_command(), now=_now())

    found = await DocumentService(repository).get_document(document.id)

    assert found == document


async def test_get_document_raises_not_found() -> None:
    service = DocumentService(InMemoryDocumentRepository())

    with pytest.raises(DocumentNotFoundError, match="not found"):
        await service.get_document(DocumentId.from_string("22222222-2222-4222-8222-222222222222"))


async def test_application_service_has_no_infrastructure_dependency() -> None:
    import workflowforge_application.documents.service as service_module

    assert "workflowforge_infrastructure" not in service_module.__dict__


class InMemoryDocumentRepository:
    def __init__(self, *, raise_duplicate_on_add: bool = False) -> None:
        self.by_id: dict[DocumentId, Document] = {}
        self.by_hash: dict[ContentHash, Document] = {}
        self.added: list[Document] = []
        self.raise_duplicate_on_add = raise_duplicate_on_add

    async def add(self, document: Document) -> Document:
        if self.raise_duplicate_on_add or document.content_hash in self.by_hash:
            msg = "duplicate"
            raise DuplicateDocumentContentError(msg)
        self.by_id[document.id] = document
        self.by_hash[document.content_hash] = document
        self.added.append(document)
        return document

    async def get_by_id(self, document_id: DocumentId) -> Document | None:
        return self.by_id.get(document_id)

    async def get_by_content_hash(self, content_hash: ContentHash) -> Document | None:
        return self.by_hash.get(content_hash)


def _command(*, original_filename: str = "example.pdf") -> DocumentRegistrationCommand:
    return DocumentRegistrationCommand(
        original_filename=original_filename,
        media_type="application/pdf",
        byte_size=123,
        content_hash=HASH,
    )


def _document() -> Document:
    return Document(
        id=DocumentId.from_string("11111111-1111-4111-8111-111111111111"),
        original_filename="existing.pdf",
        media_type="application/pdf",
        byte_size=123,
        content_hash=ContentHash(HASH),
        storage_object_key=StorageObjectKey.from_content_hash(ContentHash(HASH)),
        status=DocumentStatus.REGISTERED,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

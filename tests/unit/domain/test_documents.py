"""Document domain tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentError,
    DocumentId,
    DocumentStatus,
    InvalidDocumentTransitionError,
    StorageObjectKey,
)

HASH = "a" * 64


def test_document_can_be_registered_with_normalized_values() -> None:
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    document = Document.register(
        id=DocumentId.from_string("11111111-1111-4111-8111-111111111111"),
        original_filename=" ../Invoices/\t Example.pdf\n ",
        media_type=" Application/PDF ",
        byte_size=123,
        content_hash=ContentHash(HASH.upper()),
        storage_object_key=StorageObjectKey.from_content_hash(ContentHash(HASH)),
        now=now,
    )

    assert document.id == DocumentId(UUID("11111111-1111-4111-8111-111111111111"))
    assert document.original_filename == "Example.pdf"
    assert document.media_type == "application/pdf"
    assert document.byte_size == 123
    assert document.content_hash == ContentHash(HASH)
    assert document.storage_object_key.value == f"documents/sha256/aa/aa/{HASH}"
    assert document.status is DocumentStatus.REGISTERED
    assert document.created_at == now
    assert document.updated_at == now


def test_document_identifiers_are_strongly_typed_and_validated() -> None:
    document_id = DocumentId.new()

    assert isinstance(document_id.value, UUID)
    assert str(document_id) == str(document_id.value)

    with pytest.raises(DocumentError, match="valid UUID"):
        DocumentId.from_string("not-a-uuid")

    with pytest.raises(DocumentError, match="nil UUID"):
        DocumentId(UUID(int=0))


@pytest.mark.parametrize("filename", ["", "   ", "../", ".", "..", "\x00"])
def test_invalid_original_filenames_are_rejected(filename: str) -> None:
    with pytest.raises(DocumentError, match="filename"):
        _document(original_filename=filename)


@pytest.mark.parametrize("media_type", ["", "plain", "text/", "/plain", "bad type/plain"])
def test_invalid_media_types_are_rejected(media_type: str) -> None:
    with pytest.raises(DocumentError, match="Media type"):
        _document(media_type=media_type)


@pytest.mark.parametrize("byte_size", [-1, True])
def test_invalid_byte_sizes_are_rejected(byte_size: int) -> None:
    with pytest.raises(DocumentError, match="byte size"):
        _document(byte_size=byte_size)


@pytest.mark.parametrize("content_hash", ["", "abc", "g" * 64, "a" * 63, "a" * 65])
def test_invalid_content_hashes_are_rejected(content_hash: str) -> None:
    with pytest.raises(DocumentError, match="SHA-256"):
        ContentHash(content_hash)


@pytest.mark.parametrize(
    "storage_key",
    ["../secret", "documents\\bad", "documents//bad", "/absolute", "documents/bad?x"],
)
def test_invalid_storage_object_keys_are_rejected(storage_key: str) -> None:
    with pytest.raises(DocumentError, match="Storage object key"):
        StorageObjectKey(storage_key)


def test_document_equality_is_value_based() -> None:
    left = _document()
    right = _document()

    assert left == right


def test_registered_document_can_transition_to_stored_or_failed() -> None:
    document = _document()
    later = document.created_at + timedelta(seconds=1)

    stored = document.mark_stored(now=later)
    failed = document.mark_failed(now=later)

    assert stored.status is DocumentStatus.STORED
    assert failed.status is DocumentStatus.FAILED
    assert stored.updated_at == later
    assert failed.updated_at == later
    assert document.status is DocumentStatus.REGISTERED


def test_document_lifecycle_prevents_arbitrary_mutation() -> None:
    stored = _document().mark_stored(now=datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC))

    with pytest.raises(InvalidDocumentTransitionError, match="Cannot transition"):
        stored.mark_failed(now=datetime(2026, 1, 2, 3, 4, 7, tzinfo=UTC))


def test_document_timestamps_must_be_timezone_aware_and_monotonic() -> None:
    with pytest.raises(DocumentError, match="timezone-aware"):
        _document(now=datetime(2026, 1, 2, 3, 4, 5))

    document = _document()
    with pytest.raises(DocumentError, match="earlier"):
        document.mark_stored(now=document.created_at - timedelta(seconds=1))


def _document(
    *,
    original_filename: str = "example.pdf",
    media_type: str = "application/pdf",
    byte_size: int = 123,
    now: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
) -> Document:
    content_hash = ContentHash(HASH)
    return Document.register(
        id=DocumentId.from_string("11111111-1111-4111-8111-111111111111"),
        original_filename=original_filename,
        media_type=media_type,
        byte_size=byte_size,
        content_hash=content_hash,
        storage_object_key=StorageObjectKey.from_content_hash(content_hash),
        now=now,
    )

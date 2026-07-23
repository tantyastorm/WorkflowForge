"""Document domain tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_domain.documents import (
    ArchivedDocumentMutationError,
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentError,
    DocumentId,
    DocumentSourceType,
    DocumentStatus,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    InvalidDocumentTransitionError,
    StorageObjectKey,
    assert_artifact_consistent,
)

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_ORG = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER = UUID("11111111-1111-4111-8111-111111111111")
HASH = "a" * 64


def test_document_can_be_registered_with_tenant_and_current_version() -> None:
    now = _now()
    version = _version(now=now)

    document = Document.register(
        id=version.document_id,
        organization_id=ORG,
        display_filename=" ../Invoices/\t Example.pdf\n ",
        source_type=DocumentSourceType.UPLOAD,
        source_reference="ticket-123",
        current_version=version,
        created_by_user_id=USER,
        now=now,
    )

    assert document.organization_id == ORG
    assert document.display_filename == "Example.pdf"
    assert document.current_version_id == version.id
    assert document.status is DocumentStatus.REGISTERED
    assert document.lock_version == 1


def test_current_version_must_match_document_and_tenant() -> None:
    version = _version(organization_id=OTHER_ORG)

    with pytest.raises(DocumentError, match="tenant"):
        Document.register(
            id=version.document_id,
            organization_id=ORG,
            display_filename="example.pdf",
            source_type=DocumentSourceType.UPLOAD,
            source_reference=None,
            current_version=version,
            created_by_user_id=USER,
            now=_now(),
        )


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
        _version(original_filename=filename)


@pytest.mark.parametrize("media_type", ["", "plain", "text/", "/plain", "bad type/plain"])
def test_invalid_media_types_are_rejected(media_type: str) -> None:
    with pytest.raises(DocumentError, match="Media type"):
        _version(media_type=media_type)


@pytest.mark.parametrize("byte_size", [-1, True])
def test_invalid_byte_sizes_are_rejected(byte_size: int) -> None:
    with pytest.raises(DocumentError, match="byte size"):
        _version(byte_size=byte_size)


@pytest.mark.parametrize("content_hash", ["", "abc", "g" * 64, "a" * 63, "a" * 65])
def test_invalid_content_hashes_are_rejected(content_hash: str) -> None:
    with pytest.raises(DocumentError, match="SHA-256"):
        ContentHash(content_hash)


def test_tenant_safe_document_storage_key_is_deterministic() -> None:
    key = StorageObjectKey.for_document_content(
        organization_id=ORG,
        content_hash=ContentHash(HASH),
    )

    assert key.value == f"documents/{ORG}/sha256/aa/aa/{HASH}"

    with pytest.raises(DocumentError, match="tenant-safe"):
        StorageObjectKey.from_content_hash(ContentHash(HASH))


@pytest.mark.parametrize(
    "storage_key",
    ["../secret", "documents\\bad", "documents//bad", "/absolute", "documents/bad?x"],
)
def test_invalid_storage_object_keys_are_rejected(storage_key: str) -> None:
    with pytest.raises(DocumentError, match="Storage object key"):
        StorageObjectKey(storage_key)


def test_document_version_validates_positive_number_and_tenant_key() -> None:
    with pytest.raises(DocumentError, match="positive"):
        _version(version_number=0)

    with pytest.raises(DocumentError, match="tenant-safe"):
        _version(
            storage_object_key=StorageObjectKey.for_document_content(
                organization_id=OTHER_ORG,
                content_hash=ContentHash(HASH),
            )
        )


def test_registered_document_can_transition_to_stored_or_failed() -> None:
    document = _document()
    later = document.created_at + timedelta(seconds=1)

    stored = document.mark_stored(actor_user_id=USER, now=later)
    failed = document.mark_failed(actor_user_id=USER, now=later)

    assert stored.status is DocumentStatus.STORED
    assert failed.status is DocumentStatus.FAILED
    assert stored.lock_version == document.lock_version + 1
    assert failed.updated_by_user_id == USER
    assert document.status is DocumentStatus.REGISTERED


def test_document_lifecycle_prevents_arbitrary_mutation() -> None:
    stored = _document().mark_stored(actor_user_id=USER, now=_now(6))

    with pytest.raises(InvalidDocumentTransitionError, match="Cannot transition"):
        stored.mark_failed(actor_user_id=USER, now=_now(7))


def test_archived_document_rejects_ordinary_mutation() -> None:
    archived = _document().archive(actor_user_id=USER, now=_now(6))

    assert archived.status is DocumentStatus.ARCHIVED
    assert archived.archived_by_user_id == USER
    assert archived.lock_version == 2
    with pytest.raises(ArchivedDocumentMutationError):
        archived.mark_stored(actor_user_id=USER, now=_now(7))


def test_document_timestamps_must_be_timezone_aware_and_monotonic() -> None:
    with pytest.raises(DocumentError, match="timezone-aware"):
        _version(now=datetime(2026, 1, 2, 3, 4, 5))

    document = _document()
    with pytest.raises(DocumentError, match="earlier"):
        document.mark_stored(actor_user_id=USER, now=document.created_at - timedelta(seconds=1))


def test_artifact_requires_same_document_tenant_and_safe_storage_key() -> None:
    document = _document()
    version = _version()
    artifact_id = DocumentArtifactId.new()
    artifact = DocumentArtifact.create(
        id=artifact_id,
        organization_id=ORG,
        document_id=document.id,
        document_version_id=version.id,
        artifact_type=DocumentArtifactType.PREVIEW,
        media_type="application/pdf",
        byte_size=12,
        storage_object_key=StorageObjectKey.for_artifact(
            organization_id=ORG,
            document_id=document.id,
            artifact_type=DocumentArtifactType.PREVIEW,
            artifact_id=artifact_id,
        ),
        created_by_user_id=USER,
        metadata={"pages": 1},
        created_at=_now(),
    )

    assert_artifact_consistent(document=document, artifact=artifact, version=version)
    assert artifact.metadata["pages"] == 1

    wrong_version = _version(document_id=DocumentId.new())
    with pytest.raises(DocumentError, match="same document"):
        assert_artifact_consistent(document=document, artifact=artifact, version=wrong_version)


def _document() -> Document:
    version = _version()
    return Document.register(
        id=version.document_id,
        organization_id=ORG,
        display_filename="example.pdf",
        source_type=DocumentSourceType.UPLOAD,
        source_reference=None,
        current_version=version,
        created_by_user_id=USER,
        now=_now(),
    )


def _version(
    *,
    organization_id: UUID = ORG,
    document_id: DocumentId | None = None,
    version_number: int = 1,
    original_filename: str = "example.pdf",
    media_type: str = "application/pdf",
    byte_size: int = 123,
    now: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    storage_object_key: StorageObjectKey | None = None,
) -> DocumentVersion:
    content_hash = ContentHash(HASH)
    return DocumentVersion.create(
        id=DocumentVersionId(UUID("22222222-2222-4222-8222-222222222222")),
        organization_id=organization_id,
        document_id=document_id or DocumentId(UUID("33333333-3333-4333-8333-333333333333")),
        version_number=version_number,
        original_filename=original_filename,
        media_type=media_type,
        byte_size=byte_size,
        content_hash=content_hash,
        storage_state=DocumentStorageState.PENDING,
        created_at=now,
        created_by_user_id=USER,
        storage_object_key=storage_object_key,
    )


def _now(second: int = 5) -> datetime:
    return datetime(2026, 1, 2, 3, 4, second, tzinfo=UTC)

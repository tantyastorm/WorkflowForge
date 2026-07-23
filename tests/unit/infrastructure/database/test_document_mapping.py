"""Document persistence mapping tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Table
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentId,
    DocumentSourceType,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
)
from workflowforge_infrastructure.documents.models import (
    DocumentArtifactRecord,
    DocumentRecord,
    DocumentVersionRecord,
)
from workflowforge_infrastructure.documents.repository import (
    _artifact_from_record,
    _document_from_record,
    _record_from_artifact,
    _record_from_document,
    _record_from_version,
    _version_from_record,
)

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER = UUID("11111111-1111-4111-8111-111111111111")
HASH = "c" * 64


def test_document_record_mapping_round_trips_domain_values() -> None:
    document = _document()

    record = _record_from_document(document)
    mapped = _document_from_record(record)

    assert isinstance(record, DocumentRecord)
    assert record.id == document.id.value
    assert record.organization_id == ORG
    assert record.display_filename == "example.pdf"
    assert record.current_version_id == document.current_version_id.value
    assert mapped == document


def test_document_version_record_mapping_round_trips_domain_values() -> None:
    version = _version()

    record = _record_from_version(version)
    mapped = _version_from_record(record)

    assert isinstance(record, DocumentVersionRecord)
    assert record.content_hash == HASH
    assert record.storage_state == "pending"
    assert mapped == version


def test_document_artifact_record_mapping_round_trips_domain_values() -> None:
    artifact = _artifact()

    record = _record_from_artifact(artifact)
    mapped = _artifact_from_record(record)

    assert isinstance(record, DocumentArtifactRecord)
    assert record.metadata_json == {"pages": 1}
    assert mapped == artifact


def test_document_tables_define_expected_constraints() -> None:
    document_table = cast(Table, DocumentRecord.__table__)
    version_table = cast(Table, DocumentVersionRecord.__table__)
    artifact_table = cast(Table, DocumentArtifactRecord.__table__)
    document_constraints = {constraint.name for constraint in document_table.constraints}
    version_constraints = {constraint.name for constraint in version_table.constraints}
    artifact_constraints = {constraint.name for constraint in artifact_table.constraints}

    assert "uq_documents_organization_id_id" in document_constraints
    assert "fk_documents_organization_current_version_document_versions" in document_constraints
    assert "ck_documents_archive_state_consistent" in document_constraints
    assert "uq_document_versions_organization_content_hash" in version_constraints
    assert "uq_document_versions_organization_storage_key" in version_constraints
    assert "fk_document_versions_organization_document_documents" in version_constraints
    assert "uq_document_artifacts_organization_storage_key" in artifact_constraints
    assert "fk_document_artifacts_organization_version_document_versions" in artifact_constraints
    assert artifact_table.c.metadata.server_default is not None
    assert artifact_table.c.metadata.nullable is False


def test_document_tables_define_expected_indexes() -> None:
    document_indexes = {index.name for index in cast(Table, DocumentRecord.__table__).indexes}
    version_indexes = {index.name for index in cast(Table, DocumentVersionRecord.__table__).indexes}
    artifact_indexes = {
        index.name for index in cast(Table, DocumentArtifactRecord.__table__).indexes
    }

    assert "ix_documents_organization_status" in document_indexes
    assert "ix_documents_organization_source" in document_indexes
    assert "ix_documents_organization_updated_at" in document_indexes
    assert "ix_document_versions_document_version" in version_indexes
    assert "ix_document_versions_organization_hash" in version_indexes
    assert "ix_document_artifacts_organization_document" in artifact_indexes
    assert "ix_document_artifacts_organization_document_type" in artifact_indexes


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


def _version() -> DocumentVersion:
    content_hash = ContentHash(HASH)
    return DocumentVersion.create(
        id=DocumentVersionId(UUID("22222222-2222-4222-8222-222222222222")),
        organization_id=ORG,
        document_id=DocumentId(UUID("33333333-3333-4333-8333-333333333333")),
        version_number=1,
        original_filename="example.pdf",
        media_type="application/pdf",
        byte_size=123,
        content_hash=content_hash,
        storage_state=DocumentStorageState.PENDING,
        created_at=_now(),
        created_by_user_id=USER,
    )


def _artifact() -> DocumentArtifact:
    document_id = DocumentId(UUID("33333333-3333-4333-8333-333333333333"))
    artifact_id = DocumentArtifactId(UUID("44444444-4444-4444-8444-444444444444"))
    return DocumentArtifact.create(
        id=artifact_id,
        organization_id=ORG,
        document_id=document_id,
        document_version_id=DocumentVersionId(UUID("22222222-2222-4222-8222-222222222222")),
        artifact_type=DocumentArtifactType.PREVIEW,
        media_type="application/pdf",
        byte_size=42,
        content_hash=None,
        storage_object_key=StorageObjectKey.for_artifact(
            organization_id=ORG,
            document_id=document_id,
            artifact_type=DocumentArtifactType.PREVIEW,
            artifact_id=artifact_id,
        ),
        metadata={"pages": 1},
        created_at=_now(),
        created_by_user_id=USER,
    )


def _now() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

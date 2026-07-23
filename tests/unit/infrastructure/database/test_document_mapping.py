"""Document persistence mapping tests."""

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Table
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    DocumentStatus,
    StorageObjectKey,
)
from workflowforge_infrastructure.documents.models import DocumentRecord
from workflowforge_infrastructure.documents.repository import (
    _document_from_record,
    _record_from_document,
)

HASH = "c" * 64


def test_document_record_mapping_round_trips_domain_values() -> None:
    document = _document()

    record = _record_from_document(document)
    mapped = _document_from_record(record)

    assert isinstance(record, DocumentRecord)
    assert record.id == document.id.value
    assert record.content_hash == HASH
    assert record.status == "registered"
    assert mapped == document


def test_document_record_table_defines_expected_constraints() -> None:
    table = cast(Table, DocumentRecord.__table__)
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert [column.name for column in table.primary_key] == ["id"]
    assert "uq_documents_content_hash" in constraint_names
    assert "uq_documents_storage_object_key" in constraint_names
    assert "ix_documents_content_hash" in index_names
    assert table.c.original_filename.nullable is False
    assert table.c.byte_size.nullable is False


def _document() -> Document:
    content_hash = ContentHash(HASH)
    return Document(
        id=DocumentId.from_string("11111111-1111-4111-8111-111111111111"),
        original_filename="example.pdf",
        media_type="application/pdf",
        byte_size=123,
        content_hash=content_hash,
        storage_object_key=StorageObjectKey.from_content_hash(content_hash),
        status=DocumentStatus.REGISTERED,
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

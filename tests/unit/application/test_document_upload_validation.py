"""Document upload validation tests."""

from __future__ import annotations

import io
import zipfile

import pytest
from workflowforge_application.documents import InvalidIdempotencyKeyError, UploadValidationError
from workflowforge_application.documents.upload_validation import (
    MAX_UPLOAD_BYTES,
    normalize_upload_metadata,
    request_fingerprint,
    stream_upload,
    validate_idempotency_key,
    validate_streamed_content,
)


def test_idempotency_key_allows_bounded_safe_printable_values() -> None:
    assert validate_idempotency_key(" upload-123._: ") == "upload-123._:"

    with pytest.raises(InvalidIdempotencyKeyError):
        validate_idempotency_key("")
    with pytest.raises(InvalidIdempotencyKeyError):
        validate_idempotency_key("unsafe key")
    with pytest.raises(InvalidIdempotencyKeyError):
        validate_idempotency_key("a" * 129)


def test_upload_metadata_requires_exact_supported_media_type() -> None:
    metadata = normalize_upload_metadata(
        filename="C:\\fakepath\\Quarterly Report.PDF",
        declared_media_type="application/pdf",
    )

    assert metadata.filename == "Quarterly Report.PDF"
    assert metadata.extension == ".pdf"
    with pytest.raises(UploadValidationError, match="Declared media type"):
        normalize_upload_metadata(filename="report.pdf", declared_media_type="text/plain")


async def test_stream_upload_hashes_bytes_and_enforces_size_limit() -> None:
    upload = await stream_upload(BytesStream([b"%PDF-1.7\nbody"]), max_bytes=32, chunk_size=4)
    try:
        assert upload.byte_size == 13
        assert len(upload.content_hash.value) == 64
        assert request_fingerprint(
            content_hash=upload.content_hash,
            filename="report.pdf",
            media_type="application/pdf",
            byte_size=upload.byte_size,
        )
    finally:
        upload.body.close()

    with pytest.raises(UploadValidationError, match="too large"):
        await stream_upload(BytesStream([b"a" * (MAX_UPLOAD_BYTES + 1)]))


async def test_signature_validation_accepts_pdf_png_jpeg_text_html_and_docx() -> None:
    cases = [
        ("report.pdf", "application/pdf", b"%PDF-1.7\n"),
        ("image.png", "image/png", b"\x89PNG\r\n\x1a\nrest"),
        ("image.jpg", "image/jpeg", b"\xff\xd8payload\xff\xd9"),
        ("note.txt", "text/plain", b"plain utf-8 text"),
        ("page.html", "text/html", b"<!doctype html><html></html>"),
        ("word.docx", DOCX_MEDIA_TYPE, _docx_bytes()),
    ]

    for filename, media_type, content in cases:
        metadata = normalize_upload_metadata(filename=filename, declared_media_type=media_type)
        upload = await stream_upload(BytesStream([content]))
        try:
            validate_streamed_content(metadata=metadata, upload=upload)
        finally:
            upload.body.close()


async def test_validation_rejects_mismatched_signature_and_malformed_docx() -> None:
    metadata = normalize_upload_metadata(
        filename="report.pdf", declared_media_type="application/pdf"
    )
    upload = await stream_upload(BytesStream([b"not a pdf"]))
    try:
        with pytest.raises(UploadValidationError, match="signature"):
            validate_streamed_content(metadata=metadata, upload=upload)
    finally:
        upload.body.close()

    docx_metadata = normalize_upload_metadata(
        filename="word.docx", declared_media_type=DOCX_MEDIA_TYPE
    )
    malformed = await stream_upload(BytesStream([_docx_bytes(include_document=False)]))
    try:
        with pytest.raises(UploadValidationError, match="required entries"):
            validate_streamed_content(metadata=docx_metadata, upload=malformed)
    finally:
        malformed.body.close()


class BytesStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def read(self, size: int = -1) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if size >= 0 and len(chunk) > size:
            self._chunks.insert(0, chunk[size:])
            return chunk[:size]
        return chunk


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(*, include_document: bool = True) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        if include_document:
            archive.writestr("word/document.xml", "<document></document>")
    return output.getvalue()

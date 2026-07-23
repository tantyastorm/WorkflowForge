"""Upload validation and hashing for document intake."""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from tempfile import SpooledTemporaryFile
from typing import Protocol

from workflowforge_domain.documents import ContentHash, normalize_media_type

from workflowforge_application.documents.errors import (
    InvalidIdempotencyKeyError,
    UploadValidationError,
)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
VALIDATION_PREFIX_BYTES = 8192
IDEMPOTENCY_KEY_MAX_LENGTH = 128
DOCX_MAX_ENTRIES = 256
DOCX_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
DOCX_MAX_COMPRESSION_RATIO = 100

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CONTROL_REJECT = frozenset({"\x00", "\r", "\n"})


class SupportedUploadType(StrEnum):
    """Supported upload type labels."""

    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    TXT = "txt"
    HTML = "html"
    DOCX = "docx"


@dataclass(frozen=True, slots=True)
class UploadTypePolicy:
    """Declared media-type and extension policy."""

    upload_type: SupportedUploadType
    extensions: frozenset[str]
    media_type: str


@dataclass(frozen=True, slots=True)
class NormalizedUploadMetadata:
    """Safe upload metadata derived from multipart headers."""

    filename: str
    extension: str
    media_type: str
    upload_type: SupportedUploadType


@dataclass(frozen=True, slots=True)
class StreamedUpload:
    """Streamed upload bytes, hash, and validation samples."""

    body: SpooledTemporaryFile[bytes]
    content_hash: ContentHash
    byte_size: int
    prefix: bytes
    suffix: bytes


class AsyncUploadStream(Protocol):
    """Minimal async upload stream protocol."""

    async def read(self, size: int = -1) -> bytes:
        """Read up to size bytes."""


_POLICIES = (
    UploadTypePolicy(SupportedUploadType.PDF, frozenset({".pdf"}), "application/pdf"),
    UploadTypePolicy(SupportedUploadType.PNG, frozenset({".png"}), "image/png"),
    UploadTypePolicy(SupportedUploadType.JPEG, frozenset({".jpg", ".jpeg"}), "image/jpeg"),
    UploadTypePolicy(SupportedUploadType.TXT, frozenset({".txt"}), "text/plain"),
    UploadTypePolicy(SupportedUploadType.HTML, frozenset({".html", ".htm"}), "text/html"),
    UploadTypePolicy(
        SupportedUploadType.DOCX,
        frozenset({".docx"}),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
)


def validate_idempotency_key(value: str) -> str:
    """Validate and normalize an upload idempotency key."""

    normalized = value.strip()
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized) is None:
        msg = "Idempotency-Key must be non-empty and contain only safe printable characters."
        raise InvalidIdempotencyKeyError(msg)
    return normalized


def normalize_upload_metadata(
    *,
    filename: str | None,
    declared_media_type: str | None,
) -> NormalizedUploadMetadata:
    """Validate multipart filename and declared media type."""

    safe_filename = _normalize_upload_filename(filename)
    extension = _extension(safe_filename)
    policy = _policy_for_extension(extension)
    try:
        media_type = normalize_media_type(declared_media_type or "")
    except Exception as exc:
        raise UploadValidationError(
            "unsupported_file_type",
            "Declared media type is not supported.",
        ) from exc
    if media_type != policy.media_type:
        raise UploadValidationError(
            "media_type_mismatch",
            "Declared media type does not match the filename extension.",
        )
    return NormalizedUploadMetadata(
        filename=safe_filename,
        extension=extension,
        media_type=media_type,
        upload_type=policy.upload_type,
    )


async def stream_upload(
    stream: AsyncUploadStream,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    chunk_size: int = UPLOAD_CHUNK_SIZE,
) -> StreamedUpload:
    """Stream upload bytes into a bounded temporary file while hashing."""

    digest = hashlib.sha256()
    byte_size = 0
    prefix = bytearray()
    suffix = b""
    body: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        while True:
            chunk = await stream.read(chunk_size)
            if chunk == b"":
                break
            byte_size += len(chunk)
            if byte_size > max_bytes:
                raise UploadValidationError("file_too_large", "Uploaded file is too large.")
            digest.update(chunk)
            body.write(chunk)
            if len(prefix) < VALIDATION_PREFIX_BYTES:
                needed = VALIDATION_PREFIX_BYTES - len(prefix)
                prefix.extend(chunk[:needed])
            suffix = (suffix + chunk)[-16:]
    except UploadValidationError:
        body.close()
        raise
    except Exception as exc:
        body.close()
        raise UploadValidationError(
            "stream_read_failed",
            "Uploaded file could not be read.",
        ) from exc
    if byte_size == 0:
        body.close()
        raise UploadValidationError("empty_file", "Uploaded file must not be empty.")
    body.seek(0)
    return StreamedUpload(
        body=body,
        content_hash=ContentHash(digest.hexdigest()),
        byte_size=byte_size,
        prefix=bytes(prefix),
        suffix=suffix,
    )


def validate_streamed_content(
    *,
    metadata: NormalizedUploadMetadata,
    upload: StreamedUpload,
) -> None:
    """Validate file bytes for the supported upload type."""

    if metadata.upload_type is SupportedUploadType.PDF:
        _validate_pdf(upload.prefix)
    elif metadata.upload_type is SupportedUploadType.PNG:
        _validate_png(upload.prefix)
    elif metadata.upload_type is SupportedUploadType.JPEG:
        _validate_jpeg(upload.prefix, upload.suffix)
    elif metadata.upload_type is SupportedUploadType.TXT:
        _validate_text(upload.body, expect_html=False)
    elif metadata.upload_type is SupportedUploadType.HTML:
        _validate_text(upload.body, expect_html=True)
    elif metadata.upload_type is SupportedUploadType.DOCX:
        _validate_docx(upload.body)


def request_fingerprint(
    *,
    content_hash: ContentHash,
    filename: str,
    media_type: str,
    byte_size: int,
) -> str:
    """Create the final stable fingerprint for idempotency comparison."""

    material = f"sha256={content_hash.value};name={filename};type={media_type};size={byte_size}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _normalize_upload_filename(filename: str | None) -> str:
    if filename is None:
        raise UploadValidationError("invalid_filename", "Filename is required.")
    if any(character in filename for character in _CONTROL_REJECT):
        raise UploadValidationError("invalid_filename", "Filename contains unsafe characters.")
    normalized = unicodedata.normalize("NFC", filename).replace("\\", "/")
    normalized = normalized.rsplit("/", maxsplit=1)[-1].strip()
    normalized = "".join(
        character for character in normalized if not unicodedata.category(character).startswith("C")
    )
    normalized = " ".join(normalized.split())
    if normalized in {"", ".", ".."}:
        raise UploadValidationError("invalid_filename", "Filename is required.")
    if len(normalized) > 255:
        raise UploadValidationError("invalid_filename", "Filename is too long.")
    return normalized


def _extension(filename: str) -> str:
    if "." not in filename:
        raise UploadValidationError("unsupported_file_type", "File extension is not supported.")
    extension = "." + filename.rsplit(".", maxsplit=1)[-1].casefold()
    if extension == ".":
        raise UploadValidationError("unsupported_file_type", "File extension is not supported.")
    return extension


def _policy_for_extension(extension: str) -> UploadTypePolicy:
    for policy in _POLICIES:
        if extension in policy.extensions:
            return policy
    raise UploadValidationError("unsupported_file_type", "File extension is not supported.")


def _validate_pdf(prefix: bytes) -> None:
    if not prefix.startswith(b"%PDF-"):
        raise UploadValidationError("invalid_file_signature", "PDF signature is invalid.")
    supported_versions = {
        b"1.0",
        b"1.1",
        b"1.2",
        b"1.3",
        b"1.4",
        b"1.5",
        b"1.6",
        b"1.7",
        b"2.0",
    }
    if len(prefix) < 8 or prefix[5:8] not in supported_versions:
        raise UploadValidationError("malformed_file", "PDF header is malformed.")


def _validate_png(prefix: bytes) -> None:
    if not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        raise UploadValidationError("invalid_file_signature", "PNG signature is invalid.")


def _validate_jpeg(prefix: bytes, suffix: bytes) -> None:
    if not prefix.startswith(b"\xff\xd8"):
        raise UploadValidationError("invalid_file_signature", "JPEG signature is invalid.")
    if not suffix.endswith(b"\xff\xd9"):
        raise UploadValidationError("malformed_file", "JPEG appears truncated.")


def _validate_text(body: SpooledTemporaryFile[bytes], *, expect_html: bool) -> None:
    body.seek(0)
    data = body.read()
    body.seek(0)
    if b"\x00" in data:
        raise UploadValidationError("malformed_file", "Text upload contains null bytes.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("malformed_file", "Text upload must be valid UTF-8.") from exc
    if expect_html:
        lowered = text.casefold()
        if "<html" not in lowered and "<!doctype html" not in lowered:
            raise UploadValidationError(
                "malformed_file",
                "HTML upload is not structurally plausible.",
            )


def _validate_docx(body: SpooledTemporaryFile[bytes]) -> None:
    body.seek(0)
    data = body.read()
    body.seek(0)
    if not data.startswith(b"PK\x03\x04"):
        raise UploadValidationError("invalid_file_signature", "DOCX ZIP signature is invalid.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > DOCX_MAX_ENTRIES:
                raise UploadValidationError("malformed_file", "DOCX contains too many entries.")
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UploadValidationError("malformed_file", "DOCX required entries are missing.")
            total_uncompressed = 0
            total_compressed = 0
            for entry in entries:
                _validate_zip_entry(entry)
                total_uncompressed += entry.file_size
                total_compressed += max(entry.compress_size, 1)
            if total_uncompressed > DOCX_MAX_UNCOMPRESSED_BYTES:
                raise UploadValidationError(
                    "malformed_file",
                    "DOCX is too large after decompression.",
                )
            if total_uncompressed / total_compressed > DOCX_MAX_COMPRESSION_RATIO:
                raise UploadValidationError(
                    "malformed_file",
                    "DOCX compression ratio is suspicious.",
                )
    except UploadValidationError:
        raise
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("malformed_file", "DOCX archive is malformed.") from exc


def _validate_zip_entry(entry: zipfile.ZipInfo) -> None:
    filename = entry.filename.replace("\\", "/")
    if filename.startswith("/") or filename.startswith("../") or "/../" in filename:
        raise UploadValidationError("malformed_file", "DOCX entry path is unsafe.")
    flag_bits = entry.flag_bits
    if flag_bits & 0x1:
        raise UploadValidationError("malformed_file", "Encrypted DOCX files are not supported.")

"""Document domain model."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from workflowforge_domain.errors import DomainError

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
_STORAGE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9/_\-.]*[a-z0-9]$")


class DocumentStatus(StrEnum):
    """Current lifecycle state for document metadata."""

    REGISTERED = "registered"
    STORED = "stored"
    FAILED = "failed"


class DocumentError(DomainError):
    """Base class for document domain rule violations."""


class InvalidDocumentTransitionError(DocumentError):
    """Raised when a document lifecycle transition is not allowed."""


@dataclass(frozen=True, slots=True)
class DocumentId:
    """Strongly typed document identifier."""

    value: UUID

    @classmethod
    def new(cls) -> DocumentId:
        """Create a new random document identifier."""

        return cls(uuid4())

    @classmethod
    def from_string(cls, value: str) -> DocumentId:
        """Parse a document identifier from its string representation."""

        try:
            return cls(UUID(value))
        except ValueError as exc:
            msg = "Document identifier must be a valid UUID."
            raise DocumentError(msg) from exc

    def __post_init__(self) -> None:
        if self.value.int == 0:
            msg = "Document identifier must not be the nil UUID."
            raise DocumentError(msg)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ContentHash:
    """Deterministic SHA-256 content hash."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower()
        if not _SHA256_HEX_PATTERN.fullmatch(normalized):
            msg = "Content hash must be a 64-character SHA-256 hex digest."
            raise DocumentError(msg)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class StorageObjectKey:
    """Object-storage key metadata for future document bytes."""

    value: str

    @classmethod
    def from_content_hash(cls, content_hash: ContentHash) -> StorageObjectKey:
        """Create the deterministic storage key for a content hash."""

        digest = content_hash.value
        return cls(f"documents/sha256/{digest[:2]}/{digest[2:4]}/{digest}")

    def __post_init__(self) -> None:
        if ".." in self.value or "\\" in self.value or "//" in self.value:
            msg = "Storage object key must not contain traversal or path separator aliases."
            raise DocumentError(msg)
        if not _STORAGE_KEY_PATTERN.fullmatch(self.value):
            msg = "Storage object key contains unsupported characters."
            raise DocumentError(msg)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Document:
    """Document metadata aggregate."""

    id: DocumentId
    original_filename: str
    media_type: str
    byte_size: int
    content_hash: ContentHash
    storage_object_key: StorageObjectKey
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def register(
        cls,
        *,
        id: DocumentId,
        original_filename: str,
        media_type: str,
        byte_size: int,
        content_hash: ContentHash,
        storage_object_key: StorageObjectKey,
        now: datetime | None = None,
    ) -> Document:
        """Create registered document metadata."""

        timestamp = _normalize_timestamp(now or datetime.now(UTC), field_name="now")
        return cls(
            id=id,
            original_filename=normalize_original_filename(original_filename),
            media_type=normalize_media_type(media_type),
            byte_size=validate_byte_size(byte_size),
            content_hash=content_hash,
            storage_object_key=storage_object_key,
            status=DocumentStatus.REGISTERED,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "original_filename",
            normalize_original_filename(self.original_filename),
        )
        object.__setattr__(self, "media_type", normalize_media_type(self.media_type))
        object.__setattr__(self, "byte_size", validate_byte_size(self.byte_size))
        object.__setattr__(
            self,
            "created_at",
            _normalize_timestamp(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _normalize_timestamp(self.updated_at, field_name="updated_at"),
        )
        if self.updated_at < self.created_at:
            msg = "Document updated timestamp must not be earlier than creation timestamp."
            raise DocumentError(msg)

    def mark_stored(self, *, now: datetime | None = None) -> Document:
        """Return a copy transitioned to stored."""

        return self._transition_to(DocumentStatus.STORED, now=now)

    def mark_failed(self, *, now: datetime | None = None) -> Document:
        """Return a copy transitioned to failed."""

        return self._transition_to(DocumentStatus.FAILED, now=now)

    def _transition_to(
        self,
        status: DocumentStatus,
        *,
        now: datetime | None,
    ) -> Document:
        if self.status is not DocumentStatus.REGISTERED:
            msg = f"Cannot transition document from {self.status.value} to {status.value}."
            raise InvalidDocumentTransitionError(msg)
        timestamp = _normalize_timestamp(now or datetime.now(UTC), field_name="now")
        if timestamp < self.created_at:
            msg = "Document transition timestamp must not be earlier than creation timestamp."
            raise DocumentError(msg)
        return Document(
            id=self.id,
            original_filename=self.original_filename,
            media_type=self.media_type,
            byte_size=self.byte_size,
            content_hash=self.content_hash,
            storage_object_key=self.storage_object_key,
            status=status,
            created_at=self.created_at,
            updated_at=timestamp,
        )


def normalize_original_filename(filename: str) -> str:
    """Normalize a user-facing filename while preventing path semantics."""

    normalized = unicodedata.normalize("NFC", filename).replace("\\", "/")
    normalized = normalized.rsplit("/", maxsplit=1)[-1]
    normalized = "".join(
        character
        for character in normalized.strip()
        if not unicodedata.category(character).startswith("C")
    )
    normalized = " ".join(normalized.split())
    if normalized in {"", ".", ".."}:
        msg = "Original filename must contain a safe display name."
        raise DocumentError(msg)
    return normalized


def normalize_media_type(media_type: str) -> str:
    """Normalize and validate a media type."""

    normalized = media_type.strip().lower()
    if not _MEDIA_TYPE_PATTERN.fullmatch(normalized):
        msg = "Media type must be a valid type/subtype value."
        raise DocumentError(msg)
    return normalized


def validate_byte_size(byte_size: int) -> int:
    """Validate document byte size."""

    if isinstance(byte_size, bool) or byte_size < 0:
        msg = "Document byte size must be a non-negative integer."
        raise DocumentError(msg)
    return byte_size


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"Document {field_name} timestamp must be timezone-aware."
        raise DocumentError(msg)
    return value.astimezone(UTC)

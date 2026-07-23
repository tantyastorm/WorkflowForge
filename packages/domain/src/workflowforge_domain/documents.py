"""Document domain model."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from workflowforge_domain.errors import DomainError

DISPLAY_FILENAME_MAX_LENGTH = 255
SOURCE_REFERENCE_MAX_LENGTH = 512
ARTIFACT_METADATA_MAX_KEYS = 32
ARTIFACT_METADATA_KEY_MAX_LENGTH = 64
ARTIFACT_METADATA_VALUE_MAX_LENGTH = 512

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
_STORAGE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9/_\-.]*[a-z0-9]$")
_SAFE_SEGMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


class DocumentStatus(StrEnum):
    """Current operational state for a document aggregate."""

    REGISTERED = "registered"
    STORED = "stored"
    FAILED = "failed"
    ARCHIVED = "archived"


class DocumentSourceType(StrEnum):
    """Small source taxonomy for document registration."""

    UPLOAD = "upload"
    IMPORT = "import"
    SYSTEM = "system"


class DocumentStorageState(StrEnum):
    """Operational storage state for version or artifact objects."""

    PENDING = "pending"
    STORED = "stored"
    FAILED = "failed"


class DocumentArtifactType(StrEnum):
    """Reserved artifact classifications for real stored objects."""

    ORIGINAL = "original"
    PREVIEW = "preview"
    TEXT = "text"
    EXPORT = "export"
    OTHER = "other"


class DocumentError(DomainError):
    """Base class for document domain rule violations."""


class InvalidDocumentTransitionError(DocumentError):
    """Raised when a document lifecycle transition is not allowed."""


class ArchivedDocumentMutationError(DocumentError):
    """Raised when an archived document is mutated."""


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
        _validate_uuid(self.value, field_name="Document identifier")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class DocumentVersionId:
    """Strongly typed document-version identifier."""

    value: UUID

    @classmethod
    def new(cls) -> DocumentVersionId:
        """Create a new random document-version identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        _validate_uuid(self.value, field_name="Document version identifier")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class DocumentArtifactId:
    """Strongly typed document-artifact identifier."""

    value: UUID

    @classmethod
    def new(cls) -> DocumentArtifactId:
        """Create a new random document-artifact identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        _validate_uuid(self.value, field_name="Document artifact identifier")

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
    """Validated internal object-storage key."""

    value: str

    @classmethod
    def for_document_content(
        cls,
        *,
        organization_id: UUID,
        content_hash: ContentHash,
    ) -> StorageObjectKey:
        """Create the deterministic tenant-safe key for final document bytes."""

        _validate_uuid(organization_id, field_name="Storage key organization identifier")
        digest = content_hash.value
        return cls(f"documents/{organization_id}/sha256/{digest[:2]}/{digest[2:4]}/{digest}")

    @classmethod
    def from_content_hash(cls, content_hash: ContentHash) -> StorageObjectKey:
        """Reject legacy global storage-key construction.

        Step 2 storage keys require an organization identifier; callers should
        use :meth:`for_document_content`.
        """

        msg = "Document storage object keys require tenant-safe construction."
        raise DocumentError(msg)

    @classmethod
    def for_temporary_upload(cls, *, organization_id: UUID, upload_id: UUID) -> StorageObjectKey:
        """Create the reserved temporary object key for a future upload pipeline."""

        _validate_uuid(organization_id, field_name="Temporary key organization identifier")
        _validate_uuid(upload_id, field_name="Temporary key upload identifier")
        return cls(f"tmp/{organization_id}/{upload_id}")

    @classmethod
    def for_artifact(
        cls,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        artifact_type: DocumentArtifactType,
        artifact_id: DocumentArtifactId,
    ) -> StorageObjectKey:
        """Create the reserved key for a stored document artifact."""

        _validate_uuid(organization_id, field_name="Artifact key organization identifier")
        return cls(
            "artifacts/"
            f"{organization_id}/{document_id.value}/{artifact_type.value}/{artifact_id.value}"
        )

    def __post_init__(self) -> None:
        if ".." in self.value or "\\" in self.value or "//" in self.value:
            msg = "Storage object key must not contain traversal or path separator aliases."
            raise DocumentError(msg)
        if not _STORAGE_KEY_PATTERN.fullmatch(self.value):
            msg = "Storage object key contains unsupported characters."
            raise DocumentError(msg)
        for segment in self.value.split("/"):
            if _SAFE_SEGMENT_PATTERN.fullmatch(segment) is None:
                msg = "Storage object key contains an unsafe path segment."
                raise DocumentError(msg)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """Immutable binary metadata for one document version."""

    id: DocumentVersionId
    organization_id: UUID
    document_id: DocumentId
    version_number: int
    original_filename: str
    media_type: str
    byte_size: int
    content_hash: ContentHash
    storage_object_key: StorageObjectKey
    storage_state: DocumentStorageState
    created_at: datetime
    created_by_user_id: UUID

    @classmethod
    def create(
        cls,
        *,
        id: DocumentVersionId,
        organization_id: UUID,
        document_id: DocumentId,
        version_number: int,
        original_filename: str,
        media_type: str,
        byte_size: int,
        content_hash: ContentHash,
        storage_state: DocumentStorageState = DocumentStorageState.PENDING,
        created_at: datetime | None = None,
        created_by_user_id: UUID,
        storage_object_key: StorageObjectKey | None = None,
    ) -> DocumentVersion:
        """Create immutable version metadata."""

        key = storage_object_key or StorageObjectKey.for_document_content(
            organization_id=organization_id,
            content_hash=content_hash,
        )
        return cls(
            id=id,
            organization_id=organization_id,
            document_id=document_id,
            version_number=version_number,
            original_filename=original_filename,
            media_type=media_type,
            byte_size=byte_size,
            content_hash=content_hash,
            storage_object_key=key,
            storage_state=storage_state,
            created_at=created_at or datetime.now(UTC),
            created_by_user_id=created_by_user_id,
        )

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, field_name="Document version organization identifier")
        _validate_uuid(self.created_by_user_id, field_name="Document version creator identifier")
        if self.version_number <= 0:
            msg = "Document version number must be positive."
            raise DocumentError(msg)
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
        _ensure_key_is_tenant_safe(
            self.storage_object_key,
            organization_id=self.organization_id,
            expected_prefix=f"documents/{self.organization_id}/sha256/",
        )


@dataclass(frozen=True, slots=True)
class DocumentArtifact:
    """Metadata for a real stored document artifact."""

    id: DocumentArtifactId
    organization_id: UUID
    document_id: DocumentId
    document_version_id: DocumentVersionId | None
    artifact_type: DocumentArtifactType
    media_type: str
    byte_size: int
    content_hash: ContentHash | None
    storage_object_key: StorageObjectKey
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by_user_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        id: DocumentArtifactId,
        organization_id: UUID,
        document_id: DocumentId,
        document_version_id: DocumentVersionId | None,
        artifact_type: DocumentArtifactType,
        media_type: str,
        byte_size: int,
        storage_object_key: StorageObjectKey,
        created_by_user_id: UUID,
        content_hash: ContentHash | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> DocumentArtifact:
        """Create metadata for a real stored artifact."""

        return cls(
            id=id,
            organization_id=organization_id,
            document_id=document_id,
            document_version_id=document_version_id,
            artifact_type=artifact_type,
            media_type=media_type,
            byte_size=byte_size,
            content_hash=content_hash,
            storage_object_key=storage_object_key,
            metadata=metadata or {},
            created_at=created_at or datetime.now(UTC),
            created_by_user_id=created_by_user_id,
        )

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, field_name="Document artifact organization identifier")
        if self.created_by_user_id is None:
            msg = "Document artifact creator identifier is required."
            raise DocumentError(msg)
        _validate_uuid(self.created_by_user_id, field_name="Document artifact creator identifier")
        if not isinstance(self.artifact_type, DocumentArtifactType):
            msg = "Document artifact type is invalid."
            raise DocumentError(msg)
        object.__setattr__(self, "media_type", normalize_media_type(self.media_type))
        object.__setattr__(self, "byte_size", validate_byte_size(self.byte_size))
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(_safe_artifact_metadata(self.metadata)),
        )
        object.__setattr__(
            self,
            "created_at",
            _normalize_timestamp(self.created_at, field_name="created_at"),
        )
        _ensure_key_is_tenant_safe(
            self.storage_object_key,
            organization_id=self.organization_id,
            expected_prefix=f"artifacts/{self.organization_id}/{self.document_id.value}/",
        )


@dataclass(frozen=True, slots=True)
class Document:
    """Tenant-owned document metadata aggregate."""

    id: DocumentId
    organization_id: UUID
    display_filename: str
    source_type: DocumentSourceType
    source_reference: str | None
    status: DocumentStatus
    current_version_id: DocumentVersionId
    archived_at: datetime | None
    archived_by_user_id: UUID | None
    created_at: datetime
    created_by_user_id: UUID
    updated_at: datetime
    updated_by_user_id: UUID
    lock_version: int

    @classmethod
    def register(
        cls,
        *,
        id: DocumentId,
        organization_id: UUID,
        display_filename: str,
        source_type: DocumentSourceType,
        source_reference: str | None,
        current_version: DocumentVersion,
        created_by_user_id: UUID,
        now: datetime | None = None,
    ) -> Document:
        """Create a tenant-owned registered document aggregate."""

        if current_version.document_id != id:
            msg = "Current version must belong to the same document."
            raise DocumentError(msg)
        if current_version.organization_id != organization_id:
            msg = "Current version must belong to the same tenant."
            raise DocumentError(msg)
        timestamp = _normalize_timestamp(now or datetime.now(UTC), field_name="now")
        return cls(
            id=id,
            organization_id=organization_id,
            display_filename=display_filename,
            source_type=source_type,
            source_reference=source_reference,
            status=DocumentStatus.REGISTERED,
            current_version_id=current_version.id,
            archived_at=None,
            archived_by_user_id=None,
            created_at=timestamp,
            created_by_user_id=created_by_user_id,
            updated_at=timestamp,
            updated_by_user_id=created_by_user_id,
            lock_version=1,
        )

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, field_name="Document organization identifier")
        _validate_uuid(self.created_by_user_id, field_name="Document creator identifier")
        _validate_uuid(self.updated_by_user_id, field_name="Document updater identifier")
        object.__setattr__(
            self,
            "display_filename",
            normalize_original_filename(self.display_filename),
        )
        object.__setattr__(
            self,
            "source_reference",
            normalize_source_reference(self.source_reference),
        )
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
        if self.archived_at is not None:
            object.__setattr__(
                self,
                "archived_at",
                _normalize_timestamp(self.archived_at, field_name="archived_at"),
            )
        if self.updated_at < self.created_at:
            msg = "Document updated timestamp must not be earlier than creation timestamp."
            raise DocumentError(msg)
        if self.lock_version <= 0:
            msg = "Document lock version must be positive."
            raise DocumentError(msg)
        if self.status is DocumentStatus.ARCHIVED:
            if self.archived_at is None or self.archived_by_user_id is None:
                msg = "Archived documents require archive timestamp and actor metadata."
                raise DocumentError(msg)
            _validate_uuid(self.archived_by_user_id, field_name="Document archiver identifier")
        elif self.archived_at is not None or self.archived_by_user_id is not None:
            msg = "Only archived documents may carry archive metadata."
            raise DocumentError(msg)

    def mark_stored(self, *, actor_user_id: UUID, now: datetime | None = None) -> Document:
        """Return a copy transitioned to stored."""

        return self._transition_to(DocumentStatus.STORED, actor_user_id=actor_user_id, now=now)

    def mark_failed(self, *, actor_user_id: UUID, now: datetime | None = None) -> Document:
        """Return a copy transitioned to failed."""

        return self._transition_to(DocumentStatus.FAILED, actor_user_id=actor_user_id, now=now)

    def set_current_version(
        self,
        version: DocumentVersion,
        *,
        actor_user_id: UUID,
        now: datetime | None = None,
    ) -> Document:
        """Return a copy with a new current version."""

        self._ensure_mutable()
        if version.document_id != self.id:
            msg = "Current version must belong to the same document."
            raise DocumentError(msg)
        if version.organization_id != self.organization_id:
            msg = "Current version must belong to the same tenant."
            raise DocumentError(msg)
        return self._mutated(
            actor_user_id=actor_user_id,
            now=now,
            current_version_id=version.id,
            display_filename=version.original_filename,
            status=(
                DocumentStatus.STORED
                if version.storage_state is DocumentStorageState.STORED
                else DocumentStatus.REGISTERED
            ),
        )

    def archive(self, *, actor_user_id: UUID, now: datetime | None = None) -> Document:
        """Return an archived copy of the document."""

        self._ensure_mutable()
        timestamp = _normalize_timestamp(now or datetime.now(UTC), field_name="now")
        _validate_uuid(actor_user_id, field_name="Document archive actor identifier")
        if timestamp < self.created_at:
            msg = "Document archive timestamp must not be earlier than creation timestamp."
            raise DocumentError(msg)
        return replace(
            self,
            status=DocumentStatus.ARCHIVED,
            archived_at=timestamp,
            archived_by_user_id=actor_user_id,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def _transition_to(
        self,
        status: DocumentStatus,
        *,
        actor_user_id: UUID,
        now: datetime | None,
    ) -> Document:
        self._ensure_mutable()
        if self.status not in {DocumentStatus.REGISTERED, DocumentStatus.FAILED}:
            msg = f"Cannot transition document from {self.status.value} to {status.value}."
            raise InvalidDocumentTransitionError(msg)
        return self._mutated(actor_user_id=actor_user_id, now=now, status=status)

    def _mutated(
        self,
        *,
        actor_user_id: UUID,
        now: datetime | None,
        **changes: Any,
    ) -> Document:
        _validate_uuid(actor_user_id, field_name="Document mutation actor identifier")
        timestamp = _normalize_timestamp(now or datetime.now(UTC), field_name="now")
        if timestamp < self.created_at:
            msg = "Document mutation timestamp must not be earlier than creation timestamp."
            raise DocumentError(msg)
        return replace(
            self,
            **changes,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def _ensure_mutable(self) -> None:
        if self.status is DocumentStatus.ARCHIVED:
            msg = "Archived documents reject ordinary mutation."
            raise ArchivedDocumentMutationError(msg)


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
    if len(normalized) > DISPLAY_FILENAME_MAX_LENGTH:
        msg = f"Original filename must be at most {DISPLAY_FILENAME_MAX_LENGTH} characters."
        raise DocumentError(msg)
    return normalized


def normalize_source_reference(source_reference: str | None) -> str | None:
    """Normalize optional source reference metadata."""

    if source_reference is None:
        return None
    normalized = unicodedata.normalize("NFC", source_reference).strip()
    if not normalized:
        return None
    if len(normalized) > SOURCE_REFERENCE_MAX_LENGTH:
        msg = f"Source reference must be at most {SOURCE_REFERENCE_MAX_LENGTH} characters."
        raise DocumentError(msg)
    lowered = normalized.casefold()
    if any(part in lowered for part in {"password", "secret", "token", "authorization"}):
        msg = "Source reference must not contain secrets or authentication data."
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


def assert_artifact_consistent(
    *,
    document: Document,
    artifact: DocumentArtifact,
    version: DocumentVersion | None = None,
) -> None:
    """Validate document/artifact/version tenant consistency."""

    if artifact.organization_id != document.organization_id or artifact.document_id != document.id:
        msg = "Artifact must belong to the same document and tenant."
        raise DocumentError(msg)
    if version is None:
        return
    if artifact.document_version_id != version.id:
        msg = "Artifact version reference must match the supplied version."
        raise DocumentError(msg)
    if version.organization_id != document.organization_id or version.document_id != document.id:
        msg = "Artifact version must belong to the same document and tenant."
        raise DocumentError(msg)


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"Document {field_name} timestamp must be timezone-aware."
        raise DocumentError(msg)
    return value.astimezone(UTC)


def _validate_uuid(value: UUID, *, field_name: str) -> None:
    if value.int == 0:
        msg = f"{field_name} must not be the nil UUID."
        raise DocumentError(msg)


def _ensure_key_is_tenant_safe(
    key: StorageObjectKey,
    *,
    organization_id: UUID,
    expected_prefix: str,
) -> None:
    if str(organization_id) not in key.value or not key.value.startswith(expected_prefix):
        msg = "Storage object key must be tenant-safe for the owning organization."
        raise DocumentError(msg)


def _safe_artifact_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if len(metadata) > ARTIFACT_METADATA_MAX_KEYS:
        msg = f"Artifact metadata must have at most {ARTIFACT_METADATA_MAX_KEYS} keys."
        raise DocumentError(msg)
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_value = str(key)
        if not key_value or len(key_value) > ARTIFACT_METADATA_KEY_MAX_LENGTH:
            msg = "Artifact metadata keys are invalid."
            raise DocumentError(msg)
        if value is None or isinstance(value, bool | int | float):
            safe[key_value] = value
            continue
        if isinstance(value, str):
            if len(value) > ARTIFACT_METADATA_VALUE_MAX_LENGTH:
                msg = "Artifact metadata string value is too long."
                raise DocumentError(msg)
            safe[key_value] = value
            continue
        if isinstance(value, UUID):
            safe[key_value] = str(value)
            continue
        msg = "Artifact metadata value type is not supported."
        raise DocumentError(msg)
    return safe

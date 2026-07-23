"""Batch domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from workflowforge_domain.documents import DocumentId
from workflowforge_domain.errors import DomainError


class BatchStatus(StrEnum):
    """Batch lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class BatchError(DomainError):
    """Base class for batch domain errors."""


class ArchivedBatchMutationError(BatchError):
    """Raised when an archived batch is mutated."""


@dataclass(frozen=True, slots=True)
class BatchId:
    """Strongly typed batch identifier."""

    value: UUID

    @classmethod
    def new(cls) -> BatchId:
        """Create a new batch identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        _validate_uuid(self.value, field_name="Batch identifier")


@dataclass(frozen=True, slots=True)
class BatchDocumentId:
    """Strongly typed batch-document membership identifier."""

    value: UUID

    @classmethod
    def new(cls) -> BatchDocumentId:
        """Create a new batch-document identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        _validate_uuid(self.value, field_name="Batch document identifier")


@dataclass(frozen=True, slots=True)
class Batch:
    """Tenant-owned document batch."""

    id: BatchId
    organization_id: UUID
    name: str
    description: str | None
    status: BatchStatus
    external_reference: str | None
    created_at: datetime
    created_by_user_id: UUID
    updated_at: datetime
    updated_by_user_id: UUID
    archived_at: datetime | None
    archived_by_user_id: UUID | None
    lock_version: int

    @classmethod
    def create(
        cls,
        *,
        id: BatchId,
        organization_id: UUID,
        name: str,
        description: str | None,
        external_reference: str | None,
        created_by_user_id: UUID,
        now: datetime,
    ) -> Batch:
        """Create a new open batch."""

        timestamp = _timestamp(now)
        return cls(
            id=id,
            organization_id=organization_id,
            name=name,
            description=description,
            status=BatchStatus.OPEN,
            external_reference=external_reference,
            created_at=timestamp,
            created_by_user_id=created_by_user_id,
            updated_at=timestamp,
            updated_by_user_id=created_by_user_id,
            archived_at=None,
            archived_by_user_id=None,
            lock_version=1,
        )

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, field_name="Batch organization identifier")
        _validate_uuid(self.created_by_user_id, field_name="Batch creator identifier")
        _validate_uuid(self.updated_by_user_id, field_name="Batch updater identifier")
        object.__setattr__(self, "name", _bounded_text(self.name, "Batch name", 255, False))
        object.__setattr__(
            self,
            "description",
            _bounded_text(self.description, "Batch description", 2000, True),
        )
        object.__setattr__(
            self,
            "external_reference",
            _bounded_text(self.external_reference, "Batch external reference", 255, True),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at))
        if self.lock_version <= 0:
            msg = "Batch lock version must be positive."
            raise BatchError(msg)
        if self.status is BatchStatus.ARCHIVED:
            if self.archived_at is None or self.archived_by_user_id is None:
                msg = "Archived batches require archive metadata."
                raise BatchError(msg)
            object.__setattr__(self, "archived_at", _timestamp(self.archived_at))
        elif self.archived_at is not None or self.archived_by_user_id is not None:
            msg = "Only archived batches may carry archive metadata."
            raise BatchError(msg)

    def update(
        self,
        *,
        name: str | None,
        description: str | None,
        external_reference: str | None,
        actor_user_id: UUID,
        now: datetime,
    ) -> Batch:
        """Return a batch with updated metadata."""

        self._ensure_mutable()
        _validate_uuid(actor_user_id, field_name="Batch mutation actor identifier")
        return replace(
            self,
            name=self.name if name is None else name,
            description=description,
            external_reference=external_reference,
            updated_at=_timestamp(now),
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def archive(self, *, actor_user_id: UUID, now: datetime) -> Batch:
        """Return an archived batch."""

        self._ensure_mutable()
        timestamp = _timestamp(now)
        return replace(
            self,
            status=BatchStatus.ARCHIVED,
            archived_at=timestamp,
            archived_by_user_id=actor_user_id,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def _ensure_mutable(self) -> None:
        if self.status is BatchStatus.ARCHIVED:
            msg = "Archived batches reject ordinary mutation."
            raise ArchivedBatchMutationError(msg)


@dataclass(frozen=True, slots=True)
class BatchDocument:
    """Document membership in a batch."""

    id: BatchDocumentId
    organization_id: UUID
    batch_id: BatchId
    document_id: DocumentId
    added_at: datetime
    added_by_user_id: UUID

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, field_name="Batch document organization identifier")
        _validate_uuid(self.added_by_user_id, field_name="Batch document actor identifier")
        object.__setattr__(self, "added_at", _timestamp(self.added_at))


def _bounded_text(
    value: str | None,
    field_name: str,
    max_length: int,
    optional: bool,
) -> str | None:
    if value is None:
        if optional:
            return None
        msg = f"{field_name} is required."
        raise BatchError(msg)
    normalized = " ".join(value.strip().split())
    if not normalized:
        if optional:
            return None
        msg = f"{field_name} is required."
        raise BatchError(msg)
    if len(normalized) > max_length:
        msg = f"{field_name} must be at most {max_length} characters."
        raise BatchError(msg)
    return normalized


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "Batch timestamps must be timezone-aware."
        raise BatchError(msg)
    return value.astimezone(UTC)


def _validate_uuid(value: UUID, *, field_name: str) -> None:
    if value.int == 0:
        msg = f"{field_name} must not be the nil UUID."
        raise BatchError(msg)

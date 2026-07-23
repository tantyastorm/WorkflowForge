"""Case domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from workflowforge_domain.documents import DocumentId
from workflowforge_domain.errors import DomainError


class CaseStatus(StrEnum):
    """Case lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class CasePriority(StrEnum):
    """Case priority."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class CaseTaskStatus(StrEnum):
    """Case task status."""

    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CaseError(DomainError):
    """Base class for case domain errors."""


@dataclass(frozen=True, slots=True)
class CaseId:
    """Case identifier."""

    value: UUID

    @classmethod
    def new(cls) -> CaseId:
        return cls(uuid4())


@dataclass(frozen=True, slots=True)
class CaseDocumentId:
    """Case document membership identifier."""

    value: UUID


@dataclass(frozen=True, slots=True)
class CaseCommentId:
    """Case comment identifier."""

    value: UUID


@dataclass(frozen=True, slots=True)
class CaseTaskId:
    """Case task identifier."""

    value: UUID


@dataclass(frozen=True, slots=True)
class CaseDecisionId:
    """Case decision identifier."""

    value: UUID


@dataclass(frozen=True, slots=True)
class Case:
    """Tenant-owned case aggregate."""

    id: CaseId
    organization_id: UUID
    title: str
    summary: str | None
    status: CaseStatus
    priority: CasePriority
    external_reference: str | None
    created_at: datetime
    created_by_user_id: UUID
    updated_at: datetime
    updated_by_user_id: UUID
    closed_at: datetime | None
    closed_by_user_id: UUID | None
    archived_at: datetime | None
    archived_by_user_id: UUID | None
    lock_version: int

    @classmethod
    def create(
        cls,
        *,
        id: CaseId,
        organization_id: UUID,
        title: str,
        summary: str | None,
        priority: CasePriority,
        external_reference: str | None,
        created_by_user_id: UUID,
        now: datetime,
    ) -> Case:
        timestamp = _timestamp(now)
        return cls(
            id=id,
            organization_id=organization_id,
            title=title,
            summary=summary,
            status=CaseStatus.OPEN,
            priority=priority,
            external_reference=external_reference,
            created_at=timestamp,
            created_by_user_id=created_by_user_id,
            updated_at=timestamp,
            updated_by_user_id=created_by_user_id,
            closed_at=None,
            closed_by_user_id=None,
            archived_at=None,
            archived_by_user_id=None,
            lock_version=1,
        )

    def __post_init__(self) -> None:
        _validate_uuid(self.organization_id, "Case organization identifier")
        object.__setattr__(self, "title", _bounded_text(self.title, "Case title", 255, False))
        object.__setattr__(self, "summary", _bounded_text(self.summary, "Case summary", 4000, True))
        object.__setattr__(
            self,
            "external_reference",
            _bounded_text(self.external_reference, "Case external reference", 255, True),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", _timestamp(self.closed_at))
        if self.archived_at is not None:
            object.__setattr__(self, "archived_at", _timestamp(self.archived_at))
        if self.lock_version <= 0:
            raise CaseError("Case lock version must be positive.")

    def update(
        self,
        *,
        title: str | None,
        summary: str | None,
        priority: CasePriority | None,
        external_reference: str | None,
        actor_user_id: UUID,
        now: datetime,
    ) -> Case:
        self._ensure_mutable()
        return replace(
            self,
            title=self.title if title is None else title,
            summary=summary,
            priority=self.priority if priority is None else priority,
            external_reference=external_reference,
            updated_at=_timestamp(now),
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def close(self, *, actor_user_id: UUID, now: datetime) -> Case:
        self._ensure_mutable()
        timestamp = _timestamp(now)
        return replace(
            self,
            status=CaseStatus.CLOSED,
            closed_at=timestamp,
            closed_by_user_id=actor_user_id,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def reopen(self, *, actor_user_id: UUID, now: datetime) -> Case:
        if self.status is CaseStatus.ARCHIVED:
            raise CaseError("Archived cases cannot be reopened.")
        timestamp = _timestamp(now)
        return replace(
            self,
            status=CaseStatus.OPEN,
            closed_at=None,
            closed_by_user_id=None,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def archive(self, *, actor_user_id: UUID, now: datetime) -> Case:
        timestamp = _timestamp(now)
        return replace(
            self,
            status=CaseStatus.ARCHIVED,
            archived_at=timestamp,
            archived_by_user_id=actor_user_id,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def _ensure_mutable(self) -> None:
        if self.status is CaseStatus.ARCHIVED:
            raise CaseError("Archived cases reject ordinary mutation.")


@dataclass(frozen=True, slots=True)
class CaseDocument:
    id: CaseDocumentId
    organization_id: UUID
    case_id: CaseId
    document_id: DocumentId
    added_at: datetime
    added_by_user_id: UUID


@dataclass(frozen=True, slots=True)
class CaseComment:
    id: CaseCommentId
    organization_id: UUID
    case_id: CaseId
    body: str
    created_at: datetime
    created_by_user_id: UUID
    updated_at: datetime | None = None
    updated_by_user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CaseTask:
    id: CaseTaskId
    organization_id: UUID
    case_id: CaseId
    title: str
    description: str | None
    status: CaseTaskStatus
    assigned_to_user_id: UUID | None
    due_at: datetime | None
    completed_at: datetime | None
    completed_by_user_id: UUID | None
    created_at: datetime
    created_by_user_id: UUID
    updated_at: datetime
    updated_by_user_id: UUID
    lock_version: int

    def update(
        self,
        *,
        title: str | None,
        description: str | None,
        assigned_to_user_id: UUID | None,
        due_at: datetime | None,
        actor_user_id: UUID,
        now: datetime,
    ) -> CaseTask:
        return replace(
            self,
            title=self.title if title is None else title,
            description=description,
            assigned_to_user_id=assigned_to_user_id,
            due_at=due_at,
            updated_at=_timestamp(now),
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )

    def complete(self, *, actor_user_id: UUID, now: datetime) -> CaseTask:
        timestamp = _timestamp(now)
        return replace(
            self,
            status=CaseTaskStatus.COMPLETED,
            completed_at=timestamp,
            completed_by_user_id=actor_user_id,
            updated_at=timestamp,
            updated_by_user_id=actor_user_id,
            lock_version=self.lock_version + 1,
        )


@dataclass(frozen=True, slots=True)
class CaseDecision:
    id: CaseDecisionId
    organization_id: UUID
    case_id: CaseId
    decision_type: str
    rationale: str
    created_at: datetime
    created_by_user_id: UUID


def _bounded_text(
    value: str | None, field_name: str, max_length: int, optional: bool
) -> str | None:
    if value is None:
        if optional:
            return None
        raise CaseError(f"{field_name} is required.")
    normalized = " ".join(value.strip().split())
    if not normalized:
        if optional:
            return None
        raise CaseError(f"{field_name} is required.")
    if len(normalized) > max_length:
        raise CaseError(f"{field_name} must be at most {max_length} characters.")
    return normalized


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CaseError("Case timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _validate_uuid(value: UUID, field_name: str) -> None:
    if value.int == 0:
        raise CaseError(f"{field_name} must not be the nil UUID.")

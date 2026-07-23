"""Durable security audit event domain model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from workflowforge_domain.errors import DomainError

AUDIT_REQUEST_ID_MAX_LENGTH = 128
AUDIT_SOURCE_IP_MAX_LENGTH = 45
AUDIT_USER_AGENT_MAX_LENGTH = 512
AUDIT_METADATA_MAX_KEYS = 32
AUDIT_METADATA_KEY_MAX_LENGTH = 64
AUDIT_METADATA_STRING_MAX_LENGTH = 512
AUDIT_METADATA_LIST_MAX_ITEMS = 32
AUDIT_METADATA_MAX_DEPTH = 4
_SECRET_KEY_PARTS = frozenset(
    {
        "authorization",
        "cookie",
        "csrf",
        "digest",
        "hash",
        "password",
        "secret",
        "token",
    }
)


class AuditDomainError(DomainError):
    """Base class for audit domain validation failures."""


class InvalidAuditEvent(AuditDomainError):
    """Raised when an audit event is structurally invalid."""


class InvalidAuditMetadata(AuditDomainError):
    """Raised when audit metadata is unsafe or too large."""


class AuditEventType(StrEnum):
    """Stable security audit event taxonomy."""

    AUTHENTICATION_LOGIN_SUCCEEDED = "authentication.login_succeeded"
    AUTHENTICATION_LOGIN_FAILED = "authentication.login_failed"
    AUTHENTICATION_ACCESS_TOKEN_REJECTED = "authentication.access_token_rejected"
    SESSION_CREATED = "session.created"
    SESSION_REFRESHED = "session.refreshed"
    SESSION_REFRESH_FAILED = "session.refresh_failed"
    SESSION_REFRESH_REPLAY_DETECTED = "session.refresh_replay_detected"
    SESSION_REVOKED = "session.revoked"
    SESSION_REVOKED_ALL = "session.revoked_all"
    TENANCY_ACCESS_DENIED = "tenancy.access_denied"
    TENANCY_INACTIVE_MEMBERSHIP = "tenancy.inactive_membership"
    TENANCY_INACTIVE_ORGANIZATION = "tenancy.inactive_organization"
    AUTHORIZATION_PERMISSION_DENIED = "authorization.permission_denied"
    CREDENTIAL_PASSWORD_SET = "credential.password_set"
    CREDENTIAL_PASSWORD_REPLACED = "credential.password_replaced"
    BOOTSTRAP_OWNER_CREATED = "bootstrap.owner_created"
    BOOTSTRAP_REFUSED = "bootstrap.refused"
    AUTHENTICATION_LOGIN_RATE_LIMITED = "authentication.login_rate_limited"
    SESSION_REFRESH_RATE_LIMITED = "session.refresh_rate_limited"
    SECURITY_RATE_LIMIT_BACKEND_UNAVAILABLE = "security.rate_limit_backend_unavailable"
    DOCUMENT_REGISTERED = "document.registered"
    DOCUMENT_VERSION_CREATED = "document.version_created"
    DOCUMENT_ARCHIVED = "document.archived"
    DOCUMENT_ARTIFACT_REGISTERED = "document.artifact_registered"
    DOCUMENT_UPLOAD_STARTED = "document.upload_started"
    DOCUMENT_STORAGE_SUCCEEDED = "document.storage_succeeded"
    DOCUMENT_UPLOAD_FAILED = "document.upload_failed"
    DOCUMENT_DUPLICATE_DETECTED = "document.duplicate_detected"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_VERSION_DOWNLOADED = "document.version_downloaded"
    DOCUMENT_ARTIFACT_DOWNLOADED = "document.artifact_downloaded"
    BATCH_CREATED = "batch.created"
    BATCH_UPDATED = "batch.updated"
    BATCH_DOCUMENT_ADDED = "batch.document_added"
    BATCH_DOCUMENT_REMOVED = "batch.document_removed"
    BATCH_ARCHIVED = "batch.archived"
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_DOCUMENT_ADDED = "case.document_added"
    CASE_DOCUMENT_REMOVED = "case.document_removed"
    CASE_COMMENT_CREATED = "case.comment_created"
    CASE_TASK_CREATED = "case.task_created"
    CASE_TASK_UPDATED = "case.task_updated"
    CASE_TASK_COMPLETED = "case.task_completed"
    CASE_DECISION_CREATED = "case.decision_created"
    CASE_CLOSED = "case.closed"
    CASE_REOPENED = "case.reopened"
    CASE_ARCHIVED = "case.archived"


class AuditOutcome(StrEnum):
    """Query-friendly audit outcome."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    REPLAY_DETECTED = "replay_detected"


@dataclass(frozen=True, slots=True)
class AuditRequestContext:
    """Safe request metadata that may be attached to audit events."""

    request_id: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_string(
            self.request_id,
            max_length=AUDIT_REQUEST_ID_MAX_LENGTH,
            field_name="request_id",
        )
        _validate_optional_string(
            self.source_ip,
            max_length=AUDIT_SOURCE_IP_MAX_LENGTH,
            field_name="source_ip",
        )
        _validate_optional_string(
            self.user_agent,
            max_length=AUDIT_USER_AGENT_MAX_LENGTH,
            field_name="user_agent",
        )


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Append-only structured security audit event."""

    id: UUID
    event_type: AuditEventType
    outcome: AuditOutcome
    occurred_at: datetime
    actor_user_id: UUID | None = None
    organization_id: UUID | None = None
    session_id: UUID | None = None
    request_id: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if self.created_at is not None:
            _require_timezone_aware(self.created_at, field_name="created_at")
        AuditRequestContext(
            request_id=self.request_id,
            source_ip=self.source_ip,
            user_agent=self.user_agent,
        )
        safe_metadata = _safe_metadata(self.metadata)
        object.__setattr__(self, "metadata", MappingProxyType(safe_metadata))
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))
        if self.created_at is not None:
            object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        event_type: AuditEventType,
        outcome: AuditOutcome,
        occurred_at: datetime,
        actor_user_id: UUID | None = None,
        organization_id: UUID | None = None,
        session_id: UUID | None = None,
        request_context: AuditRequestContext | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Create an audit event from application-safe inputs."""

        context = request_context or AuditRequestContext()
        return cls(
            id=id,
            event_type=event_type,
            outcome=outcome,
            occurred_at=occurred_at,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            session_id=session_id,
            request_id=context.request_id,
            source_ip=context.source_ip,
            user_agent=context.user_agent,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return (
            "AuditEvent("
            f"id={self.id!r}, event_type={self.event_type.value!r}, "
            f"outcome={self.outcome.value!r}, occurred_at={self.occurred_at!r}, "
            f"actor_user_id={self.actor_user_id!r}, organization_id={self.organization_id!r}, "
            f"session_id={self.session_id!r})"
        )


def _validate_optional_string(value: str | None, *, max_length: int, field_name: str) -> None:
    if value is None:
        return
    if not value or len(value) > max_length:
        msg = f"{field_name} must be between 1 and {max_length} characters."
        raise InvalidAuditEvent(msg)


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware."
        raise InvalidAuditEvent(msg)


def _safe_metadata(metadata: Mapping[str, Any], *, depth: int = 0) -> dict[str, Any]:
    if depth > AUDIT_METADATA_MAX_DEPTH:
        msg = f"Audit metadata nesting must be at most {AUDIT_METADATA_MAX_DEPTH} levels."
        raise InvalidAuditMetadata(msg)
    if len(metadata) > AUDIT_METADATA_MAX_KEYS:
        msg = f"Audit metadata must have at most {AUDIT_METADATA_MAX_KEYS} keys."
        raise InvalidAuditMetadata(msg)
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_value = str(key)
        if not key_value or len(key_value) > AUDIT_METADATA_KEY_MAX_LENGTH:
            msg = f"Audit metadata keys must be between 1 and {AUDIT_METADATA_KEY_MAX_LENGTH}."
            raise InvalidAuditMetadata(msg)
        safe[key_value] = _safe_metadata_value(key_value, value, depth=depth)
    return safe


def _safe_metadata_value(key: str, value: Any, *, depth: int) -> Any:
    lowered = key.casefold()
    if any(secret_part in lowered for secret_part in _SECRET_KEY_PARTS):
        msg = "Audit metadata contains a prohibited secret-like key."
        raise InvalidAuditMetadata(msg)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) > AUDIT_METADATA_STRING_MAX_LENGTH:
            msg = "Audit metadata string value is too long."
            raise InvalidAuditMetadata(msg)
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        _require_timezone_aware(value, field_name="metadata datetime value")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        if depth >= AUDIT_METADATA_MAX_DEPTH:
            msg = f"Audit metadata nesting must be at most {AUDIT_METADATA_MAX_DEPTH} levels."
            raise InvalidAuditMetadata(msg)
        return _safe_metadata(value, depth=depth + 1)
    if isinstance(value, list | tuple):
        if depth >= AUDIT_METADATA_MAX_DEPTH:
            msg = f"Audit metadata nesting must be at most {AUDIT_METADATA_MAX_DEPTH} levels."
            raise InvalidAuditMetadata(msg)
        if len(value) > AUDIT_METADATA_LIST_MAX_ITEMS:
            msg = "Audit metadata list value is too long."
            raise InvalidAuditMetadata(msg)
        return [_safe_metadata_value(key, item, depth=depth + 1) for item in value]
    msg = "Audit metadata value type is not supported."
    raise InvalidAuditMetadata(msg)

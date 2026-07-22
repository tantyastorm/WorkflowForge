"""Audit domain model tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_domain.audit import (
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    AuditRequestContext,
    InvalidAuditEvent,
    InvalidAuditMetadata,
)
from workflowforge_domain.identity import Permission

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
EVENT_ID = UUID("99999999-9999-4999-8999-999999999999")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_audit_event_accepts_safe_structured_metadata_and_redacts_repr() -> None:
    event = AuditEvent.create(
        id=EVENT_ID,
        event_type=AuditEventType.AUTHENTICATION_LOGIN_SUCCEEDED,
        outcome=AuditOutcome.SUCCESS,
        occurred_at=NOW,
        actor_user_id=USER_ID,
        request_context=AuditRequestContext(
            request_id="request-1",
            source_ip="127.0.0.1",
            user_agent="testclient",
        ),
        metadata={"reason": "password_login", "attempt": 1},
    )

    assert event.metadata["reason"] == "password_login"
    assert event.request_id == "request-1"
    assert "password_login" not in repr(event)


def test_audit_event_rejects_naive_timestamps_and_oversized_request_fields() -> None:
    with pytest.raises(InvalidAuditEvent):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=datetime(2026, 1, 2, 3, 4, 5),
        )

    with pytest.raises(InvalidAuditEvent):
        AuditRequestContext(request_id="x" * 129)


def test_audit_metadata_rejects_secret_like_keys_and_unsupported_values() -> None:
    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"refresh_token": "do-not-store"},
        )

    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"exception": RuntimeError("no repr dumps")},
        )


def test_audit_metadata_rejects_oversized_keys_values_lists_and_nesting() -> None:
    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"x" * 65: "value"},
        )

    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"reason": "x" * 513},
        )

    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"permissions": ["organization.read"] * 33},
        )

    with pytest.raises(InvalidAuditMetadata):
        AuditEvent.create(
            id=EVENT_ID,
            event_type=AuditEventType.SESSION_REFRESH_FAILED,
            outcome=AuditOutcome.FAILURE,
            occurred_at=NOW,
            metadata={"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}},
        )


def test_audit_metadata_serializes_safe_uuid_datetime_and_enum_values() -> None:
    event = AuditEvent.create(
        id=EVENT_ID,
        event_type=AuditEventType.AUTHORIZATION_PERMISSION_DENIED,
        outcome=AuditOutcome.DENIED,
        occurred_at=NOW,
        metadata={
            "user_id": USER_ID,
            "occurred": NOW,
            "permission": Permission.SECURITY_MANAGE,
        },
    )

    assert event.metadata == {
        "user_id": str(USER_ID),
        "occurred": NOW.isoformat(),
        "permission": "security.manage",
    }

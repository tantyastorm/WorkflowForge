"""API audit helper tests."""

from uuid import UUID

from starlette.requests import Request
from workflowforge_api.audit import audit_request_context, record_independent_audit_event
from workflowforge_application.audit import AuditPersistenceError
from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome


def test_audit_request_context_bounds_and_normalizes_request_metadata() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/demo",
        "headers": [(b"user-agent", b"a" * 600)],
        "client": ("127.000.000.001", 12345),
    }
    request = Request(scope)
    request.state.correlation_id = "request-id"

    context = audit_request_context(request)

    assert context.request_id == "request-id"
    assert context.source_ip is None
    assert context.user_agent == "a" * 512


async def test_record_independent_audit_event_swallows_persistence_failures() -> None:
    audit = FailingAuditRecorder()

    await record_independent_audit_event(
        audit=audit,
        event_id=UUID("11111111-1111-4111-8111-111111111111"),
        event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
        outcome=AuditOutcome.FAILURE,
        metadata={"reason": "test"},
    )

    assert audit.attempts == 1


class FailingAuditRecorder:
    def __init__(self) -> None:
        self.attempts = 0

    async def record(self, event: AuditEvent) -> None:
        self.attempts += 1
        assert event.metadata["reason"] == "test"
        raise AuditPersistenceError("nope")

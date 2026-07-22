"""API audit adapter tests."""

from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from workflowforge_api.audit import audit_request_context, record_independent_audit_event
from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome


def test_audit_request_context_uses_correlation_direct_client_and_bounded_user_agent() -> None:
    request = _request(
        client=("127.0.0.1", 12345),
        headers=[
            (b"user-agent", b"x" * 600),
            (b"x-forwarded-for", b"203.0.113.10"),
        ],
        correlation_id="request-123",
    )

    context = audit_request_context(request)

    assert context.request_id == "request-123"
    assert context.source_ip == "127.0.0.1"
    assert context.user_agent == "x" * 512


def test_audit_request_context_ignores_missing_or_invalid_client() -> None:
    request = _request(client=None, headers=[(b"user-agent", b"<script>")])

    context = audit_request_context(request)

    assert context.source_ip is None
    assert context.user_agent == "<script>"


async def test_independent_audit_helper_logs_and_preserves_original_flow_on_failure() -> None:
    recorder = FailingAuditRecorder()

    await record_independent_audit_event(
        audit=recorder,
        event_id=recorder.event_id,
        event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
        outcome=AuditOutcome.FAILURE,
    )

    assert recorder.attempted is True


class FailingAuditRecorder:
    event_id = UUID("99999999-9999-4999-8999-999999999999")

    def __init__(self) -> None:
        self.attempted = False

    async def record(self, event: AuditEvent) -> None:
        from workflowforge_application.audit import AuditPersistenceError

        self.attempted = True
        raise AuditPersistenceError("audit failed")


def _request(
    *,
    client: tuple[str, int] | None,
    headers: list[tuple[bytes, bytes]],
    correlation_id: str | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": client,
    }
    request = Request(scope)
    if correlation_id is not None:
        request.state.correlation_id = correlation_id
    return request

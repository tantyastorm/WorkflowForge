"""Diagnostic task contract tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workflowforge_contracts import (
    DIAGNOSTIC_ECHO_TASK_NAME,
    SCHEDULER_HEARTBEAT_TASK_NAME,
    DiagnosticEchoPayload,
    DiagnosticEchoResult,
    SchedulerHeartbeatResult,
)


def test_diagnostic_echo_payload_accepts_bounded_message() -> None:
    payload = DiagnosticEchoPayload(message="hello")

    assert payload.message == "hello"


@pytest.mark.parametrize("message", ["", "x" * 257])
def test_diagnostic_echo_payload_rejects_invalid_message(message: str) -> None:
    with pytest.raises(ValidationError):
        DiagnosticEchoPayload(message=message)


def test_diagnostic_echo_payload_rejects_arbitrary_fields() -> None:
    with pytest.raises(ValidationError):
        DiagnosticEchoPayload.model_validate({"message": "hello", "payload": {"run": "code"}})


def test_diagnostic_echo_result_shape() -> None:
    result = DiagnosticEchoResult(
        message="hello",
        task_id="task-id",
        task_name=DIAGNOSTIC_ECHO_TASK_NAME,
        processed_at=datetime.now(UTC),
        worker="worker",
        correlation_id="correlation",
    )

    assert result.model_dump(mode="json")["task_name"] == DIAGNOSTIC_ECHO_TASK_NAME
    assert result.processed_at.tzinfo is not None


def test_scheduler_heartbeat_result_shape() -> None:
    result = SchedulerHeartbeatResult(
        key="workflowforge:diagnostics:scheduler:last_seen",
        observed_at=datetime.now(UTC),
        ttl_seconds=90,
    )

    assert result.key == "workflowforge:diagnostics:scheduler:last_seen"
    assert result.ttl_seconds == 90
    assert SCHEDULER_HEARTBEAT_TASK_NAME == "system.diagnostics.scheduler_heartbeat"

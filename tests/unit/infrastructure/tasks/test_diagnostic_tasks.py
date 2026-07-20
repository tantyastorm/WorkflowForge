"""Diagnostic Celery task tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workflowforge_contracts import DIAGNOSTIC_ECHO_TASK_NAME
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.tasks import create_celery_app


def test_diagnostic_echo_task_returns_safe_result() -> None:
    app = create_celery_app(Settings())
    app.conf.task_always_eager = True
    task = app.tasks[DIAGNOSTIC_ECHO_TASK_NAME]

    result = task.apply(
        args=({"message": "hello"},),
        headers={"correlation_id": "correlation"},
    ).get()

    assert result["message"] == "hello"
    assert result["task_name"] == DIAGNOSTIC_ECHO_TASK_NAME
    assert result["task_id"]
    assert result["worker"]
    assert result["correlation_id"] == "correlation"
    assert datetime.fromisoformat(result["processed_at"]).astimezone(UTC).tzinfo is UTC
    assert "secret" not in str(result).lower()


def test_diagnostic_echo_task_rejects_invalid_message() -> None:
    app = create_celery_app(Settings())
    app.conf.task_always_eager = True
    task = app.tasks[DIAGNOSTIC_ECHO_TASK_NAME]

    with pytest.raises(ValidationError):
        task.apply(args=({"message": ""},)).get(propagate=True)


def test_diagnostic_echo_task_rejects_arbitrary_payload() -> None:
    app = create_celery_app(Settings())
    app.conf.task_always_eager = True
    task = app.tasks[DIAGNOSTIC_ECHO_TASK_NAME]

    with pytest.raises(ValidationError):
        task.apply(args=({"message": "hello", "extra": "not allowed"},)).get(propagate=True)

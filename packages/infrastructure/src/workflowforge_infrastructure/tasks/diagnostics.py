"""Diagnostic Celery tasks."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from redis import Redis
from workflowforge_contracts import (
    DIAGNOSTIC_ECHO_TASK_NAME,
    SCHEDULER_HEARTBEAT_TASK_NAME,
    DiagnosticEchoPayload,
    DiagnosticEchoResult,
    SchedulerHeartbeatResult,
)

from workflowforge_infrastructure.config import Settings

logger = structlog.get_logger(__name__)


def register_diagnostic_tasks(app: Any, settings: Settings) -> None:
    """Register safe diagnostic tasks on a Celery app."""

    if DIAGNOSTIC_ECHO_TASK_NAME not in app.tasks:

        def diagnostic_echo(self: Any, payload: Mapping[str, object]) -> dict[str, Any]:
            checked_payload = DiagnosticEchoPayload.model_validate(payload)
            request = self.request
            correlation_id = _correlation_id_from_request(request)
            result = DiagnosticEchoResult(
                message=checked_payload.message,
                task_id=str(request.id or "unknown"),
                task_name=DIAGNOSTIC_ECHO_TASK_NAME,
                processed_at=datetime.now(UTC),
                worker=str(request.hostname or "unknown"),
                correlation_id=correlation_id,
            )
            logger.info(
                "diagnostic_task_completed",
                task_id=result.task_id,
                task_name=result.task_name,
                correlation_id=correlation_id,
            )
            return result.model_dump(mode="json")

        app.task(name=DIAGNOSTIC_ECHO_TASK_NAME, bind=True)(diagnostic_echo)

    if SCHEDULER_HEARTBEAT_TASK_NAME not in app.tasks:

        def scheduler_heartbeat(self: Any) -> dict[str, Any]:
            observed_at = datetime.now(UTC)
            client = Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                db=settings.redis.db,
                password=(
                    settings.redis.password.get_secret_value()
                    if settings.redis.password is not None
                    else None
                ),
                ssl=settings.redis.ssl,
                socket_timeout=settings.redis.socket_timeout_seconds,
                socket_connect_timeout=settings.redis.socket_timeout_seconds,
                decode_responses=True,
            )
            try:
                client.set(
                    settings.scheduler.heartbeat_key,
                    observed_at.isoformat(),
                    ex=settings.scheduler.heartbeat_ttl_seconds,
                )
            finally:
                client.close()

            result = SchedulerHeartbeatResult(
                key=settings.scheduler.heartbeat_key,
                observed_at=observed_at,
                ttl_seconds=settings.scheduler.heartbeat_ttl_seconds,
            )
            logger.info(
                "scheduler_heartbeat_recorded",
                task_id=str(self.request.id or "unknown"),
                task_name=SCHEDULER_HEARTBEAT_TASK_NAME,
            )
            return result.model_dump(mode="json")

        app.task(name=SCHEDULER_HEARTBEAT_TASK_NAME, bind=True)(scheduler_heartbeat)


def _correlation_id_from_headers(headers: Mapping[str, object] | None) -> str | None:
    if headers is None:
        return None
    for key in ("correlation_id", "x-correlation-id", "X-Correlation-ID"):
        value = headers.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _correlation_id_from_request(request: Any) -> str | None:
    headers = _correlation_id_from_headers(
        cast("Mapping[str, object] | None", getattr(request, "headers", None))
    )
    if headers is not None:
        return headers

    getter = getattr(request, "get", None)
    if not callable(getter):
        return None
    for key in ("x-correlation-id", "X-Correlation-ID"):
        value = getter(key)
        if isinstance(value, str) and value:
            return value
    return None

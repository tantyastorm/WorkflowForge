"""API adapters for security audit recording."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request
from workflowforge_application.audit import AuditPersistenceError, AuditRecorder
from workflowforge_domain.audit import (
    AUDIT_USER_AGENT_MAX_LENGTH,
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    AuditRequestContext,
)
from workflowforge_infrastructure.audit import SqlAlchemyAuditRepository
from workflowforge_infrastructure.database import async_session_scope, create_async_session_factory

_LOGGER = structlog.get_logger("workflowforge_api.audit")


def audit_request_context(request: Request) -> AuditRequestContext:
    """Return bounded, application-safe request metadata for audit."""

    request_id = getattr(request.state, "correlation_id", None)
    source_ip = _normalize_source_ip(request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    return AuditRequestContext(
        request_id=request_id if isinstance(request_id, str) else None,
        source_ip=source_ip,
        user_agent=user_agent[:AUDIT_USER_AGENT_MAX_LENGTH] if user_agent else None,
    )


class IndependentSqlAlchemyAuditRecorder(AuditRecorder):
    """Persist audit events in a dedicated transaction."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(self, event: AuditEvent) -> None:
        """Append and commit one audit event independently."""

        session_factory = create_async_session_factory(self._engine)
        async with async_session_scope(session_factory) as session:
            try:
                await SqlAlchemyAuditRepository(session).record(event)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                if isinstance(exc, AuditPersistenceError):
                    raise
                msg = "Audit event could not be persisted."
                raise AuditPersistenceError(msg) from exc


async def record_independent_audit_event(
    *,
    audit: AuditRecorder,
    event_id: UUID,
    event_type: AuditEventType,
    outcome: AuditOutcome,
    actor_user_id: UUID | None = None,
    organization_id: UUID | None = None,
    session_id: UUID | None = None,
    request_context: AuditRequestContext | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Persist a best-effort independent audit event.

    Failure and denial audit persistence must not replace the public
    authentication or authorization response. Failures are logged structurally
    with request-local correlation context by structlog middleware.
    """

    event = AuditEvent.create(
        id=event_id,
        event_type=event_type,
        outcome=outcome,
        occurred_at=datetime.now(UTC),
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        session_id=session_id,
        request_context=request_context,
        metadata=metadata or {},
    )
    try:
        await audit.record(event)
    except AuditPersistenceError:
        _LOGGER.exception(
            "security_audit_persistence_failed",
            event_type=event_type.value,
            outcome=outcome.value,
        )


def _normalize_source_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        return None

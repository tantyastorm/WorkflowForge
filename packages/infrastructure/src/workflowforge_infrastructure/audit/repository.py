"""SQLAlchemy audit recorder and query adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.audit import AuditPersistenceError, AuditQuery, AuditRecorder
from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome

from workflowforge_infrastructure.audit.models import SecurityAuditEventRecord

MAX_AUDIT_QUERY_LIMIT = 100


class SqlAlchemyAuditRepository(AuditRecorder, AuditQuery):
    """SQLAlchemy implementation of append-only audit ports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEvent) -> None:
        """Append one event without committing the caller's transaction."""

        self._session.add(_record_from_event(event))
        try:
            await self._session.flush()
        except SQLAlchemyError as exc:
            msg = "Audit event could not be persisted."
            raise AuditPersistenceError(msg) from exc

    async def list_recent(self, *, limit: int = 50) -> list[AuditEvent]:
        """Return recent events newest first."""

        return await self._list(select(SecurityAuditEventRecord), limit=limit)

    async def list_for_user(self, user_id: UUID, *, limit: int = 50) -> list[AuditEvent]:
        """Return recent events for one actor newest first."""

        return await self._list(
            select(SecurityAuditEventRecord).where(
                SecurityAuditEventRecord.actor_user_id == user_id
            ),
            limit=limit,
        )

    async def list_for_organization(
        self,
        organization_id: UUID,
        *,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Return recent events for one organization newest first."""

        return await self._list(
            select(SecurityAuditEventRecord).where(
                SecurityAuditEventRecord.organization_id == organization_id
            ),
            limit=limit,
        )

    async def list_by_event_type(
        self,
        event_type: AuditEventType,
        *,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Return recent events of one type newest first."""

        return await self._list(
            select(SecurityAuditEventRecord).where(
                SecurityAuditEventRecord.event_type == event_type.value
            ),
            limit=limit,
        )

    async def _list(
        self,
        statement: Select[tuple[SecurityAuditEventRecord]],
        *,
        limit: int,
    ) -> list[AuditEvent]:
        bounded_limit = _bounded_limit(limit)
        result = await self._session.execute(
            statement.order_by(
                SecurityAuditEventRecord.occurred_at.desc(),
                SecurityAuditEventRecord.id.desc(),
            ).limit(bounded_limit)
        )
        return [_event_from_record(record) for record in result.scalars()]


def _bounded_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_AUDIT_QUERY_LIMIT)


def _record_from_event(event: AuditEvent) -> SecurityAuditEventRecord:
    return SecurityAuditEventRecord(
        id=event.id,
        event_type=event.event_type.value,
        outcome=event.outcome.value,
        occurred_at=event.occurred_at,
        actor_user_id=event.actor_user_id,
        organization_id=event.organization_id,
        session_id=event.session_id,
        request_id=event.request_id,
        source_ip=event.source_ip,
        user_agent=event.user_agent,
        metadata_json=dict(event.metadata),
        created_at=event.created_at or datetime.now(UTC),
    )


def _event_from_record(record: SecurityAuditEventRecord) -> AuditEvent:
    return AuditEvent(
        id=record.id,
        event_type=AuditEventType(record.event_type),
        outcome=AuditOutcome(record.outcome),
        occurred_at=record.occurred_at.astimezone(UTC),
        actor_user_id=record.actor_user_id,
        organization_id=record.organization_id,
        session_id=record.session_id,
        request_id=record.request_id,
        source_ip=record.source_ip,
        user_agent=record.user_agent,
        metadata=record.metadata_json,
        created_at=record.created_at.astimezone(UTC),
    )

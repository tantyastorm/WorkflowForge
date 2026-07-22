"""Audit application ports."""

from typing import Protocol
from uuid import UUID

from workflowforge_domain.audit import AuditEvent, AuditEventType


class AuditRecorder(Protocol):
    """Append-only audit write port.

    Implementations record into the caller's current transaction unless they
    explicitly document an independent transaction boundary.
    """

    async def record(self, event: AuditEvent) -> None:
        """Append one audit event."""


class AuditQuery(Protocol):
    """Bounded audit read/query port for internal use."""

    async def list_recent(self, *, limit: int = 50) -> list[AuditEvent]:
        """Return recent events newest first."""

    async def list_for_user(self, user_id: UUID, *, limit: int = 50) -> list[AuditEvent]:
        """Return recent events for one actor newest first."""

    async def list_for_organization(
        self,
        organization_id: UUID,
        *,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Return recent events for one organization newest first."""

    async def list_by_event_type(
        self,
        event_type: AuditEventType,
        *,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Return recent events of one type newest first."""

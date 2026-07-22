"""SQLAlchemy security hardening repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.security import (
    BootstrapState,
    IdentityBootstrapRepository,
    SessionCleanupRepository,
)

from workflowforge_infrastructure.identity.models import (
    AuthSessionRecord,
    OrganizationRecord,
    RefreshTokenRecordModel,
    UserRecord,
)


class SqlAlchemyIdentityBootstrapRepository(IdentityBootstrapRepository):
    """SQLAlchemy implementation of bootstrap guard queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_bootstrap_lock(self) -> None:
        """Acquire a PostgreSQL transaction-scoped lock for first-owner bootstrap."""

        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": 917202611},
        )

    async def bootstrap_state(self) -> BootstrapState:
        """Return counts of identity bootstrap guard tables."""

        users = await self._session.execute(select(func.count()).select_from(UserRecord))
        organizations = await self._session.execute(
            select(func.count()).select_from(OrganizationRecord)
        )
        return BootstrapState(
            users=int(users.scalar_one()),
            organizations=int(organizations.scalar_one()),
        )


class SqlAlchemySessionCleanupRepository(SessionCleanupRepository):
    """SQLAlchemy implementation of bounded session cleanup operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_expired_refresh_tokens(self, *, before: datetime, limit: int) -> int:
        """Delete expired refresh-token rows in stable bounded order."""

        ids = await self._ids(
            select(RefreshTokenRecordModel.id)
            .where(RefreshTokenRecordModel.expires_at < before)
            .order_by(RefreshTokenRecordModel.expires_at, RefreshTokenRecordModel.id)
            .limit(limit)
        )
        if not ids:
            return 0
        await self._session.execute(
            delete(RefreshTokenRecordModel).where(RefreshTokenRecordModel.id.in_(ids))
        )
        await self._session.flush()
        return len(ids)

    async def delete_expired_sessions(self, *, before: datetime, limit: int) -> int:
        """Delete expired sessions after retention, preserving active sessions."""

        ids = await self._ids(
            select(AuthSessionRecord.id)
            .where(AuthSessionRecord.expires_at < before)
            .order_by(AuthSessionRecord.expires_at, AuthSessionRecord.id)
            .limit(limit)
        )
        if not ids:
            return 0
        await self._session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.id.in_(ids)))
        await self._session.flush()
        return len(ids)

    async def delete_revoked_sessions(self, *, before: datetime, limit: int) -> int:
        """Delete old revoked sessions after retention."""

        ids = await self._ids(
            select(AuthSessionRecord.id)
            .where(
                AuthSessionRecord.revoked_at.is_not(None),
                AuthSessionRecord.revoked_at < before,
            )
            .order_by(AuthSessionRecord.revoked_at, AuthSessionRecord.id)
            .limit(limit)
        )
        if not ids:
            return 0
        await self._session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.id.in_(ids)))
        await self._session.flush()
        return len(ids)

    async def _ids(self, statement: Select[tuple[UUID]]) -> list[UUID]:
        result = await self._session.execute(statement)
        return list(result.scalars())

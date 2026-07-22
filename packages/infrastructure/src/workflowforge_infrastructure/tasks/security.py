"""Security maintenance Celery tasks."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy.exc import SQLAlchemyError
from workflowforge_application.security import (
    CleanupExpiredSessions,
    CleanupExpiredSessionsCommand,
)

from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.database import (
    SqlAlchemyTransactionManager,
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import SystemClock
from workflowforge_infrastructure.security import SqlAlchemySessionCleanupRepository

SECURITY_CLEANUP_TASK_NAME = "security.sessions.cleanup"

logger = structlog.get_logger(__name__)


def register_security_tasks(app: Any, settings: Settings) -> None:
    """Register security maintenance tasks."""

    if SECURITY_CLEANUP_TASK_NAME in app.tasks:
        return

    def cleanup_sessions(self: Any) -> dict[str, int]:
        result = asyncio.run(_cleanup_sessions(settings))
        logger.info(
            "security_session_cleanup_completed",
            task_id=str(self.request.id or "unknown"),
            expired_refresh_tokens_deleted=result["expired_refresh_tokens_deleted"],
            expired_sessions_deleted=result["expired_sessions_deleted"],
            revoked_sessions_deleted=result["revoked_sessions_deleted"],
        )
        return result

    app.task(
        name=SECURITY_CLEANUP_TASK_NAME,
        bind=True,
        autoretry_for=(SQLAlchemyError, OSError),
        retry_backoff=True,
        retry_jitter=False,
        retry_kwargs={"max_retries": 3},
    )(cleanup_sessions)


async def _cleanup_sessions(settings: Settings) -> dict[str, int]:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        use_case = CleanupExpiredSessions(
            repository=SqlAlchemySessionCleanupRepository(session),
            transaction=SqlAlchemyTransactionManager(session),
            clock=SystemClock(),
        )
        result = await use_case(
            CleanupExpiredSessionsCommand(
                batch_limit=settings.cleanup.session_batch_limit,
                expired_session_retention=timedelta(
                    seconds=settings.cleanup.expired_session_retention_seconds
                ),
                revoked_session_retention=timedelta(
                    seconds=settings.cleanup.revoked_session_retention_seconds
                ),
            )
        )
        return {
            "expired_refresh_tokens_deleted": result.expired_refresh_tokens_deleted,
            "expired_sessions_deleted": result.expired_sessions_deleted,
            "revoked_sessions_deleted": result.revoked_sessions_deleted,
        }
    finally:
        await session.close()
        await dispose_async_engine(engine)

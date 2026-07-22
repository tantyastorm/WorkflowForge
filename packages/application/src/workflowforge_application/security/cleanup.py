"""Authentication session cleanup use case."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from workflowforge_application.identity import Clock, TransactionManager
from workflowforge_application.security.ports import SessionCleanupRepository, SessionCleanupResult


@dataclass(frozen=True, slots=True)
class CleanupExpiredSessionsCommand:
    """Input for bounded authentication cleanup."""

    batch_limit: int = 500
    expired_session_retention: timedelta = timedelta(days=7)
    revoked_session_retention: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if self.batch_limit <= 0 or self.batch_limit > 10_000:
            msg = "Cleanup batch_limit must be between 1 and 10000."
            raise ValueError(msg)
        if self.expired_session_retention < timedelta(0):
            msg = "Expired session retention must be non-negative."
            raise ValueError(msg)
        if self.revoked_session_retention < timedelta(0):
            msg = "Revoked session retention must be non-negative."
            raise ValueError(msg)


class CleanupExpiredSessions:
    """Delete expired refresh credentials and old inactive sessions in bounded batches."""

    def __init__(
        self,
        *,
        repository: SessionCleanupRepository,
        transaction: TransactionManager,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._transaction = transaction
        self._clock = clock

    async def __call__(
        self,
        command: CleanupExpiredSessionsCommand | None = None,
    ) -> SessionCleanupResult:
        """Run one cleanup batch and commit the bounded deletion transaction."""

        cleanup_command = command or CleanupExpiredSessionsCommand()
        try:
            now = _utc(self._clock.now())
            expired_refresh_tokens = await self._repository.delete_expired_refresh_tokens(
                before=now,
                limit=cleanup_command.batch_limit,
            )
            expired_sessions = await self._repository.delete_expired_sessions(
                before=now - cleanup_command.expired_session_retention,
                limit=cleanup_command.batch_limit,
            )
            revoked_sessions = await self._repository.delete_revoked_sessions(
                before=now - cleanup_command.revoked_session_retention,
                limit=cleanup_command.batch_limit,
            )
            await self._transaction.commit()
            return SessionCleanupResult(
                expired_refresh_tokens_deleted=expired_refresh_tokens,
                expired_sessions_deleted=expired_sessions,
                revoked_sessions_deleted=revoked_sessions,
            )
        except Exception:
            await self._transaction.rollback()
            raise


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "Cleanup clock must return a timezone-aware timestamp."
        raise ValueError(msg)
    return value.astimezone(UTC)

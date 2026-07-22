"""Authentication cleanup use-case tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from workflowforge_application.security import CleanupExpiredSessions, CleanupExpiredSessionsCommand

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.mark.asyncio
async def test_cleanup_deletes_bounded_expired_refresh_tokens_and_old_sessions() -> None:
    repository = FakeCleanupRepository(refresh_tokens=2, expired_sessions=3, revoked_sessions=4)
    transaction = FakeTransaction()
    use_case = CleanupExpiredSessions(
        repository=repository,
        transaction=transaction,
        clock=FakeClock(NOW),
    )

    result = await use_case(
        CleanupExpiredSessionsCommand(
            batch_limit=25,
            expired_session_retention=timedelta(days=7),
            revoked_session_retention=timedelta(days=30),
        )
    )

    assert result.expired_refresh_tokens_deleted == 2
    assert result.expired_sessions_deleted == 3
    assert result.revoked_sessions_deleted == 4
    assert repository.calls == [
        ("refresh", NOW, 25),
        ("expired", NOW - timedelta(days=7), 25),
        ("revoked", NOW - timedelta(days=30), 25),
    ]
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_cleanup_rolls_back_when_delete_fails() -> None:
    transaction = FakeTransaction()
    use_case = CleanupExpiredSessions(
        repository=FakeCleanupRepository(fail=True),
        transaction=transaction,
        clock=FakeClock(NOW),
    )

    with pytest.raises(RuntimeError, match="delete failed"):
        await use_case()

    assert transaction.commits == 0
    assert transaction.rollbacks == 1


def test_cleanup_command_validates_limits_and_retentions() -> None:
    with pytest.raises(ValueError, match="batch_limit"):
        CleanupExpiredSessionsCommand(batch_limit=0)
    with pytest.raises(ValueError, match="Expired session retention"):
        CleanupExpiredSessionsCommand(expired_session_retention=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="Revoked session retention"):
        CleanupExpiredSessionsCommand(revoked_session_retention=timedelta(seconds=-1))


class FakeCleanupRepository:
    def __init__(
        self,
        *,
        refresh_tokens: int = 0,
        expired_sessions: int = 0,
        revoked_sessions: int = 0,
        fail: bool = False,
    ) -> None:
        self.refresh_tokens = refresh_tokens
        self.expired_sessions = expired_sessions
        self.revoked_sessions = revoked_sessions
        self.fail = fail
        self.calls: list[tuple[str, datetime, int]] = []

    async def delete_expired_refresh_tokens(self, *, before: datetime, limit: int) -> int:
        if self.fail:
            raise RuntimeError("delete failed")
        self.calls.append(("refresh", before, limit))
        return self.refresh_tokens

    async def delete_expired_sessions(self, *, before: datetime, limit: int) -> int:
        self.calls.append(("expired", before, limit))
        return self.expired_sessions

    async def delete_revoked_sessions(self, *, before: datetime, limit: int) -> int:
        self.calls.append(("revoked", before, limit))
        return self.revoked_sessions


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

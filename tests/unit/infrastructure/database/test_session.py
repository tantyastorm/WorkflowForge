"""Async session helper tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_infrastructure.config import DatabaseSettings
from workflowforge_infrastructure.database import (
    async_session_scope,
    create_async_database_engine,
    create_async_session_factory,
)


def test_create_async_session_factory() -> None:
    engine = create_async_database_engine(DatabaseSettings())

    try:
        session_factory = create_async_session_factory(engine)
        session = session_factory()

        try:
            assert isinstance(session, AsyncSession)
            assert session.sync_session.expire_on_commit is False
            assert session.sync_session.autoflush is False
        finally:
            session.sync_session.close()
    finally:
        engine.sync_engine.dispose()


async def test_session_scope_rolls_back_and_closes_on_exception() -> None:
    session = AsyncMock(spec=AsyncSession)

    def session_factory() -> AsyncSession:
        return session

    with pytest.raises(RuntimeError, match="boom"):
        async with async_session_scope(session_factory):
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()

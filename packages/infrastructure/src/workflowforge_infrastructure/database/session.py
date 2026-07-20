"""Async database session helpers."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

AsyncSessionFactory = async_sessionmaker[AsyncSession]


def create_async_session_factory(engine: AsyncEngine) -> AsyncSessionFactory:
    """Create a typed async session factory.

    Sessions do not commit implicitly. Application use cases own transaction
    boundaries and should commit only after successful orchestration.
    """

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@asynccontextmanager
async def async_session_scope(
    session_factory: Callable[[], AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one async session, rolling back on exceptions and always closing."""

    session = session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

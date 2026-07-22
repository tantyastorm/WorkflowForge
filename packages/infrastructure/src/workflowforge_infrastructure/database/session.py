"""Async database session helpers."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from workflowforge_application.identity import TransactionManager

AsyncSessionFactory = async_sessionmaker[AsyncSession]


class SqlAlchemyTransactionManager(TransactionManager):
    """Commit or roll back the current SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Commit the current transaction."""

        await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""

        await self._session.rollback()


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

"""Document repository integration tests."""

from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from workflowforge_application.documents import DuplicateDocumentContentError
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    DocumentStatus,
    StorageObjectKey,
)
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.documents import SqlAlchemyDocumentRepository

from tests.integration.database.utils import require_postgresql

HASH = "d" * 64


@pytest.mark.integration
async def test_document_repository_add_and_get_by_id_and_content_hash() -> None:
    engine, session = await _session()
    document = _document()

    try:
        repository = SqlAlchemyDocumentRepository(session)
        added = await repository.add(document)
        await session.commit()

        assert added == document
        assert await repository.get_by_id(document.id) == document
        assert await repository.get_by_content_hash(document.content_hash) == document
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_document_repository_raises_duplicate_content_error() -> None:
    engine, session = await _session()

    try:
        repository = SqlAlchemyDocumentRepository(session)
        await repository.add(_document())
        await session.commit()

        duplicate = _document(
            document_id="22222222-2222-4222-8222-222222222222",
            storage_hash="e" * 64,
        )
        with pytest.raises(DuplicateDocumentContentError):
            await repository.add(duplicate)
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_document_repository_transaction_rollback_discards_uncommitted_add() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(require_postgresql())
    session_factory = create_async_session_factory(engine)
    document = _document(document_id="33333333-3333-4333-8333-333333333333", content_hash="f" * 64)

    try:
        async with session_factory() as session:
            await SqlAlchemyDocumentRepository(session).add(document)
            await session.rollback()

        async with session_factory() as session:
            found = await SqlAlchemyDocumentRepository(session).get_by_id(document.id)
            assert found is None
    finally:
        await dispose_async_engine(engine)


async def _session() -> tuple[AsyncEngine, AsyncSession]:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    return engine, session


def _document(
    *,
    document_id: str = "11111111-1111-4111-8111-111111111111",
    content_hash: str = HASH,
    storage_hash: str | None = None,
) -> Document:
    hash_value = ContentHash(content_hash)
    storage_hash_value = ContentHash(storage_hash or content_hash)
    return Document(
        id=DocumentId.from_string(document_id),
        original_filename="example.pdf",
        media_type="application/pdf",
        byte_size=123,
        content_hash=hash_value,
        storage_object_key=StorageObjectKey.from_content_hash(storage_hash_value),
        status=DocumentStatus.REGISTERED,
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

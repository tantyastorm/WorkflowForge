"""Document repository integration tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from workflowforge_application.documents import DuplicateDocumentContentError
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentId,
    DocumentSourceType,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
)
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.documents import SqlAlchemyDocumentRepository

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
HASH = "d" * 64
ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_ORG = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = DocumentId(UUID("33333333-3333-4333-8333-333333333333"))
VERSION_ID = DocumentVersionId(UUID("44444444-4444-4444-8444-444444444444"))


@pytest.mark.integration
async def test_document_repository_persists_tenant_document_and_version() -> None:
    engine, session = await _session()
    document, version = _document_pair()

    try:
        await _seed_identity(session)
        repository = SqlAlchemyDocumentRepository(session)
        added = await repository.add_document(document, version)
        await session.commit()

        assert added == document
        assert (
            await repository.get_document(organization_id=ORG, document_id=document.id) == document
        )
        assert (
            await repository.get_version(
                organization_id=ORG,
                document_id=document.id,
                version_id=version.id,
            )
            == version
        )
        assert (
            await repository.find_document_by_tenant_content_hash(
                organization_id=ORG,
                content_hash=version.content_hash,
            )
            == document
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_same_hash_in_different_tenants_succeeds() -> None:
    engine, session = await _session()

    try:
        await _seed_identity(session)
        repository = SqlAlchemyDocumentRepository(session)
        first_document, first_version = _document_pair()
        second_document, second_version = _document_pair(
            organization_id=OTHER_ORG,
            user_id=OTHER_USER,
            document_id=DocumentId(UUID("33333333-3333-4333-8333-444444444444")),
            version_id=DocumentVersionId(UUID("44444444-4444-4444-8444-555555555555")),
        )
        await repository.add_document(first_document, first_version)
        await repository.add_document(second_document, second_version)
        await session.commit()

        assert (
            await repository.find_document_by_tenant_content_hash(
                organization_id=ORG,
                content_hash=ContentHash(HASH),
            )
            == first_document
        )
        assert (
            await repository.find_document_by_tenant_content_hash(
                organization_id=OTHER_ORG,
                content_hash=ContentHash(HASH),
            )
            == second_document
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_same_hash_in_same_tenant_raises_duplicate_content_error() -> None:
    engine, session = await _session()

    try:
        await _seed_identity(session)
        repository = SqlAlchemyDocumentRepository(session)
        await repository.add_document(*_document_pair())
        await session.commit()

        duplicate = _document_pair(
            document_id=DocumentId(UUID("33333333-3333-4333-8333-555555555555")),
            version_id=DocumentVersionId(UUID("44444444-4444-4444-8444-666666666666")),
        )
        with pytest.raises(DuplicateDocumentContentError):
            await repository.add_document(*duplicate)
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_repository_isolates_cross_tenant_document_lookup() -> None:
    engine, session = await _session()
    document, version = _document_pair()

    try:
        await _seed_identity(session)
        repository = SqlAlchemyDocumentRepository(session)
        await repository.add_document(document, version)
        await session.commit()

        assert (
            await repository.get_document(organization_id=OTHER_ORG, document_id=document.id)
            is None
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_artifact_and_archive_persistence() -> None:
    engine, session = await _session()
    document, version = _document_pair()

    try:
        await _seed_identity(session)
        repository = SqlAlchemyDocumentRepository(session)
        await repository.add_document(document, version)
        artifact_id = DocumentArtifactId(UUID("55555555-5555-4555-8555-555555555555"))
        artifact = DocumentArtifact.create(
            id=artifact_id,
            organization_id=ORG,
            document_id=document.id,
            document_version_id=version.id,
            artifact_type=DocumentArtifactType.PREVIEW,
            media_type="application/pdf",
            byte_size=7,
            storage_object_key=StorageObjectKey.for_artifact(
                organization_id=ORG,
                document_id=document.id,
                artifact_type=DocumentArtifactType.PREVIEW,
                artifact_id=artifact_id,
            ),
            metadata={"pages": 1},
            created_at=NOW,
            created_by_user_id=USER,
        )
        await repository.add_artifact(artifact)
        archived = document.archive(actor_user_id=USER, now=NOW.replace(second=6))
        await repository.archive_document(archived)
        await session.commit()

        assert (
            await repository.get_artifact(
                organization_id=ORG,
                document_id=document.id,
                artifact_id=artifact_id,
            )
            == artifact
        )
        assert (
            await repository.get_document(organization_id=ORG, document_id=document.id) == archived
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_document_repository_transaction_rollback_discards_uncommitted_add() -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(require_postgresql())
    session_factory = create_async_session_factory(engine)
    document, version = _document_pair()

    try:
        async with session_factory() as session:
            await _clean_head_schema(session)
            await _seed_identity(session)
            await SqlAlchemyDocumentRepository(session).add_document(document, version)
            await session.rollback()

        async with session_factory() as session:
            found = await SqlAlchemyDocumentRepository(session).get_document(
                organization_id=ORG,
                document_id=document.id,
            )
            assert found is None
    finally:
        await dispose_async_engine(engine)


async def _session() -> tuple[AsyncEngine, AsyncSession]:
    settings = require_postgresql()
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    await _clean_head_schema(session)
    return engine, session


async def _clean_head_schema(session: AsyncSession) -> None:
    await session.execute(
        text(
            "TRUNCATE document_artifacts, document_versions, documents, "
            "security_audit_events, refresh_tokens, auth_sessions, password_credentials, "
            "memberships, organizations, users RESTART IDENTITY CASCADE"
        )
    )
    await session.commit()


async def _seed_identity(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO users (id, email, normalized_email, display_name, is_active, "
            "created_at, updated_at) VALUES "
            "(:user_id, 'owner@example.com', 'owner@example.com', 'Owner', true, :now, :now), "
            "(:other_user_id, 'other@example.com', 'other@example.com', 'Other', true, :now, :now)"
        ),
        {"user_id": USER, "other_user_id": OTHER_USER, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) "
            "VALUES (:org, 'Org', 'org', true, :now, :now), "
            "(:other_org, 'Other Org', 'other-org', true, :now, :now)"
        ),
        {"org": ORG, "other_org": OTHER_ORG, "now": NOW},
    )


def _document_pair(
    *,
    organization_id: UUID = ORG,
    user_id: UUID = USER,
    document_id: DocumentId = DOCUMENT_ID,
    version_id: DocumentVersionId = VERSION_ID,
    content_hash: str = HASH,
) -> tuple[Document, DocumentVersion]:
    hash_value = ContentHash(content_hash)
    version = DocumentVersion.create(
        id=version_id,
        organization_id=organization_id,
        document_id=document_id,
        version_number=1,
        original_filename="example.pdf",
        media_type="application/pdf",
        byte_size=123,
        content_hash=hash_value,
        storage_state=DocumentStorageState.PENDING,
        created_at=NOW,
        created_by_user_id=user_id,
    )
    document = Document.register(
        id=document_id,
        organization_id=organization_id,
        display_filename="example.pdf",
        source_type=DocumentSourceType.UPLOAD,
        source_reference=None,
        current_version=version,
        created_by_user_id=user_id,
        now=NOW,
    )
    return document, version


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

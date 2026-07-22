"""Security audit repository integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete
from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome
from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
    Organization,
    OrganizationSlug,
    RefreshTokenDigest,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    SessionId,
    User,
)
from workflowforge_infrastructure.audit import SqlAlchemyAuditRepository
from workflowforge_infrastructure.audit.models import SecurityAuditEventRecord
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    SqlAlchemyOrganizationRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from workflowforge_infrastructure.identity.models import OrganizationRecord, UserRecord

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
FIRST_EVENT_ID = UUID("99999999-9999-4999-8999-999999999991")
SECOND_EVENT_ID = UUID("99999999-9999-4999-8999-999999999992")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_repository_appends_and_queries_newest_first() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(require_postgresql())
    session = create_async_session_factory(engine)()
    try:
        repository = SqlAlchemyAuditRepository(session)
        await repository.record(
            AuditEvent.create(
                id=FIRST_EVENT_ID,
                event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                occurred_at=NOW,
                request_context=None,
                metadata={"reason": "invalid_credentials"},
            )
        )
        await repository.record(
            AuditEvent.create(
                id=SECOND_EVENT_ID,
                event_type=AuditEventType.SESSION_REFRESH_FAILED,
                outcome=AuditOutcome.FAILURE,
                occurred_at=NOW + timedelta(seconds=1),
                metadata={"reason": "missing_cookie"},
            )
        )
        await session.commit()

        recent = await repository.list_recent(limit=10)
        refresh_failures = await repository.list_by_event_type(
            AuditEventType.SESSION_REFRESH_FAILED,
            limit=10,
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)

    assert [event.id for event in recent] == [SECOND_EVENT_ID, FIRST_EVENT_ID]
    assert [event.id for event in refresh_failures] == [SECOND_EVENT_ID]
    assert recent[0].metadata == {"reason": "missing_cookie"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_query_tie_ordering_and_limit_bounds_are_deterministic() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(require_postgresql())
    session = create_async_session_factory(engine)()
    try:
        repository = SqlAlchemyAuditRepository(session)
        await repository.record(
            AuditEvent.create(
                id=FIRST_EVENT_ID,
                event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                occurred_at=NOW,
            )
        )
        await repository.record(
            AuditEvent.create(
                id=SECOND_EVENT_ID,
                event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
                outcome=AuditOutcome.FAILURE,
                occurred_at=NOW,
            )
        )
        await session.commit()

        zero_limit = await repository.list_recent(limit=0)
        large_limit = await repository.list_recent(limit=1000)
    finally:
        await session.close()
        await dispose_async_engine(engine)

    assert [event.id for event in zero_limit] == [SECOND_EVENT_ID]
    assert [event.id for event in large_limit] == [SECOND_EVENT_ID, FIRST_EVENT_ID]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_evidence_survives_user_session_and_organization_deletion() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(require_postgresql())
    session = create_async_session_factory(engine)()
    try:
        await SqlAlchemyUserRepository(session).add(
            User.create(
                id=USER_ID,
                email=EmailAddress("ada@example.com"),
                display_name="Ada Lovelace",
                now=NOW,
            )
        )
        await SqlAlchemyOrganizationRepository(session).add(
            Organization.create(
                id=ORG_ID,
                name="Org A",
                slug=OrganizationSlug("org-a"),
                now=NOW,
            )
        )
        await SqlAlchemySessionRepository(session).add(
            session=AuthSession.create(
                id=SessionId(SESSION_ID),
                user_id=USER_ID,
                now=NOW,
                expires_at=NOW + timedelta(hours=1),
            ),
            refresh_token=_refresh_token(),
        )
        await SqlAlchemyAuditRepository(session).record(
            AuditEvent.create(
                id=FIRST_EVENT_ID,
                event_type=AuditEventType.SESSION_CREATED,
                outcome=AuditOutcome.SUCCESS,
                occurred_at=NOW,
                actor_user_id=USER_ID,
                organization_id=ORG_ID,
                session_id=SESSION_ID,
            )
        )
        await session.commit()

        await session.execute(delete(UserRecord).where(UserRecord.id == USER_ID))
        await session.execute(delete(OrganizationRecord).where(OrganizationRecord.id == ORG_ID))
        await session.commit()
        record = await session.get(SecurityAuditEventRecord, FIRST_EVENT_ID)
    finally:
        await session.close()
        await dispose_async_engine(engine)

    assert record is not None
    assert record.actor_user_id is None
    assert record.session_id is None
    assert record.organization_id is None


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config


def _refresh_token() -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(UUID("55555555-5555-4555-8555-555555555555")),
        session_id=SessionId(SESSION_ID),
        token_family_id=RefreshTokenFamilyId(UUID("66666666-6666-4666-8666-666666666666")),
        token_digest=RefreshTokenDigest("a" * 64),
        generation=0,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

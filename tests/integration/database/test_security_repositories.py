"""Security repository integration tests."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from workflowforge_application.security import BootstrapOwner, BootstrapOwnerCommand
from workflowforge_application.security.errors import BootstrapRefusedError
from workflowforge_domain.audit import AuditEventType
from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
    MembershipStatus,
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
    SqlAlchemyTransactionManager,
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.database.session import AsyncSessionFactory
from workflowforge_infrastructure.identity import (
    Argon2PasswordHasher,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    Uuid4Generator,
)
from workflowforge_infrastructure.identity.models import (
    AuthSessionRecord,
    MembershipRecord,
    OrganizationRecord,
    PasswordCredentialRecord,
    RefreshTokenRecordModel,
    UserRecord,
)
from workflowforge_infrastructure.security import (
    SqlAlchemyIdentityBootstrapRepository,
    SqlAlchemySessionCleanupRepository,
)

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTIVE_SESSION_ID = UUID("44444444-4444-4444-8444-111111111111")
EXPIRED_SESSION_ID = UUID("44444444-4444-4444-8444-222222222222")
REVOKED_SESSION_ID = UUID("44444444-4444-4444-8444-333333333333")
OTHER_SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
PASSWORD = "correct horse battery staple"


@pytest.mark.integration
async def test_bootstrap_repository_lock_and_state_counts() -> None:
    engine, session = await _session()

    try:
        bootstrap = SqlAlchemyIdentityBootstrapRepository(session)
        await bootstrap.acquire_bootstrap_lock()
        state = await bootstrap.bootstrap_state()
        assert state.users == 0
        assert state.organizations == 0

        await SqlAlchemyUserRepository(session).add(_user())
        await session.flush()

        state = await bootstrap.bootstrap_state()
        assert state.users == 1
        assert state.organizations == 0
    finally:
        await session.rollback()
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_bootstrap_concurrent_attempts_create_exactly_one_owner() -> None:
    settings = require_postgresql()
    _reset_database()
    engine = create_async_database_engine(settings)
    session_factory = create_async_session_factory(engine)

    try:
        results = await asyncio.gather(
            _run_bootstrap(session_factory, "owner-a@example.com", "alpha-org"),
            _run_bootstrap(session_factory, "owner-b@example.com", "beta-org"),
        )

        successes = [result for result in results if result == "created"]
        refusals = [result for result in results if result == "refused"]
        assert successes == ["created"]
        assert refusals == ["refused"]

        async with session_factory() as session:
            assert await _count_users(session) == 1
            assert await _count_organizations(session) == 1
            assert await _count_active_owner_memberships(session) == 1
            assert await _count_password_credentials(session) == 1
            assert (
                await _count_audit_events(
                    session,
                    AuditEventType.BOOTSTRAP_OWNER_CREATED,
                )
                == 1
            )
            assert await _count_audit_events(session, AuditEventType.BOOTSTRAP_REFUSED) == 1
    finally:
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_bootstrap_rolls_back_when_commit_fails_after_audit_flush() -> None:
    settings = require_postgresql()
    _reset_database()
    engine = create_async_database_engine(settings)
    session_factory = create_async_session_factory(engine)

    try:
        async with session_factory() as session:
            use_case = BootstrapOwner(
                state=SqlAlchemyIdentityBootstrapRepository(session),
                users=SqlAlchemyUserRepository(session),
                organizations=SqlAlchemyOrganizationRepository(session),
                memberships=SqlAlchemyMembershipRepository(session),
                credentials=SqlAlchemyPasswordCredentialRepository(session),
                password_hasher=Argon2PasswordHasher(),
                audit=SqlAlchemyAuditRepository(session),
                transaction=FailingCommitTransaction(session),
                ids=Uuid4Generator(),
            )
            with pytest.raises(RuntimeError, match="commit failed"):
                await use_case(
                    BootstrapOwnerCommand(
                        email="owner@example.com",
                        display_name="Owner",
                        password=PASSWORD,
                        organization_name="example",
                        organization_slug="example",
                    )
                )

        async with session_factory() as session:
            assert await _count_users(session) == 0
            assert await _count_organizations(session) == 0
            assert await _count_active_owner_memberships(session) == 0
            assert await _count_password_credentials(session) == 0
            assert (
                await _count_audit_events(
                    session,
                    AuditEventType.BOOTSTRAP_OWNER_CREATED,
                )
                == 0
            )
    finally:
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_cleanup_repository_batches_and_is_idempotent() -> None:
    engine, session = await _session()

    try:
        await SqlAlchemyUserRepository(session).add(_user())
        sessions = SqlAlchemySessionRepository(session)
        await sessions.add(
            session=_auth_session(ACTIVE_SESSION_ID, expires_at=NOW + timedelta(days=1)),
            refresh_token=_refresh_token(
                "a" * 64,
                ACTIVE_SESSION_ID,
                expires_at=NOW + timedelta(days=1),
            ),
        )
        await sessions.add(
            session=_auth_session(
                EXPIRED_SESSION_ID,
                now=NOW - timedelta(days=11),
                expires_at=NOW - timedelta(days=10),
            ),
            refresh_token=_refresh_token(
                "b" * 64,
                EXPIRED_SESSION_ID,
                issued_at=NOW - timedelta(days=2),
                expires_at=NOW - timedelta(days=1),
            ),
        )
        await sessions.add(
            session=_auth_session(
                REVOKED_SESSION_ID,
                now=NOW - timedelta(days=45),
                expires_at=NOW + timedelta(days=1),
            ).revoke(now=NOW - timedelta(days=40)),
            refresh_token=_refresh_token(
                "c" * 64,
                REVOKED_SESSION_ID,
                expires_at=NOW + timedelta(days=1),
            ),
        )
        await sessions.add(
            session=_auth_session(OTHER_SESSION_ID, expires_at=NOW + timedelta(days=1)),
            refresh_token=_refresh_token(
                "d" * 64,
                OTHER_SESSION_ID,
                issued_at=NOW - timedelta(days=2),
                expires_at=NOW - timedelta(days=1),
            ),
        )
        await session.commit()

        cleanup = SqlAlchemySessionCleanupRepository(session)

        assert await cleanup.delete_expired_refresh_tokens(before=NOW, limit=1) == 1
        assert await cleanup.delete_expired_refresh_tokens(before=NOW, limit=1) == 1
        assert await cleanup.delete_expired_refresh_tokens(before=NOW, limit=1) == 0
        assert (
            await cleanup.delete_expired_sessions(
                before=NOW - timedelta(days=7),
                limit=100,
            )
            == 1
        )
        assert (
            await cleanup.delete_revoked_sessions(
                before=NOW - timedelta(days=30),
                limit=100,
            )
            == 1
        )
        assert (
            await cleanup.delete_expired_sessions(
                before=NOW - timedelta(days=7),
                limit=100,
            )
            == 0
        )
        assert (
            await cleanup.delete_revoked_sessions(
                before=NOW - timedelta(days=30),
                limit=100,
            )
            == 0
        )
        await session.commit()

        assert await _count_auth_sessions(session) == 2
        assert await _count_refresh_tokens(session) == 1
    finally:
        await session.close()
        await dispose_async_engine(engine)


async def _session() -> tuple[AsyncEngine, AsyncSession]:
    settings = require_postgresql()
    _reset_database()
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    return engine, session


async def _run_bootstrap(
    session_factory: AsyncSessionFactory,
    email: str,
    slug: str,
) -> str:
    session = session_factory()
    try:
        use_case = BootstrapOwner(
            state=SqlAlchemyIdentityBootstrapRepository(session),
            users=SqlAlchemyUserRepository(session),
            organizations=SqlAlchemyOrganizationRepository(session),
            memberships=SqlAlchemyMembershipRepository(session),
            credentials=SqlAlchemyPasswordCredentialRepository(session),
            password_hasher=Argon2PasswordHasher(),
            audit=SqlAlchemyAuditRepository(session),
            transaction=SqlAlchemyTransactionManager(session),
            ids=Uuid4Generator(),
        )
        await use_case(
            BootstrapOwnerCommand(
                email=email,
                display_name="Owner",
                password=PASSWORD,
                organization_name=slug,
                organization_slug=slug,
            )
        )
        return "created"
    except BootstrapRefusedError:
        return "refused"
    finally:
        await session.close()


def _user() -> User:
    return User.create(
        id=USER_ID,
        email=EmailAddress("ada@example.com"),
        display_name="Ada Lovelace",
        now=NOW,
    )


def _auth_session(
    session_id: UUID,
    *,
    expires_at: datetime,
    now: datetime = NOW,
) -> AuthSession:
    return AuthSession.create(
        id=SessionId(session_id),
        user_id=USER_ID,
        now=now,
        expires_at=expires_at,
    )


def _refresh_token(
    digest: str,
    session_id: UUID,
    *,
    expires_at: datetime,
    issued_at: datetime = NOW,
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(UUID(f"55555555-5555-4555-8555-{digest[0] * 12}")),
        session_id=SessionId(session_id),
        token_family_id=RefreshTokenFamilyId(UUID(f"66666666-6666-4666-8666-{digest[0] * 12}")),
        token_digest=RefreshTokenDigest(digest),
        generation=0,
        issued_at=issued_at,
        expires_at=expires_at,
    )


async def _count_auth_sessions(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(AuthSessionRecord))
    return int(result.scalar_one())


async def _count_refresh_tokens(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(RefreshTokenRecordModel))
    return int(result.scalar_one())


async def _count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(UserRecord))
    return int(result.scalar_one())


async def _count_organizations(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(OrganizationRecord))
    return int(result.scalar_one())


async def _count_active_owner_memberships(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(MembershipRecord)
        .where(
            MembershipRecord.role == "owner",
            MembershipRecord.status == MembershipStatus.ACTIVE.value,
        )
    )
    return int(result.scalar_one())


async def _count_password_credentials(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(PasswordCredentialRecord))
    return int(result.scalar_one())


async def _count_audit_events(session: AsyncSession, event_type: AuditEventType) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(SecurityAuditEventRecord)
        .where(SecurityAuditEventRecord.event_type == event_type.value)
    )
    return int(result.scalar_one())


def _reset_database() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")


class FailingCommitTransaction(SqlAlchemyTransactionManager):
    async def commit(self) -> None:
        raise RuntimeError("commit failed")


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

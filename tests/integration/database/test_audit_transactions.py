"""Security audit transaction integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from workflowforge_application.audit import AuditPersistenceError
from workflowforge_application.identity import (
    AccessTokenClaims,
    AuthenticatedUser,
    IssuedRefreshToken,
    MissingIdentityReferenceError,
    RefreshSession,
    RefreshSessionCommand,
    SessionLifecyclePolicy,
    StartUserSession,
    StartUserSessionCommand,
)
from workflowforge_domain.audit import AuditEvent, AuditEventType
from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
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
from workflowforge_infrastructure.identity import (
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from workflowforge_infrastructure.identity.models import AuthSessionRecord, RefreshTokenRecordModel

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
MISSING_USER_ID = UUID("11111111-1111-4111-8111-999999999999")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("55555555-5555-4555-8555-555555555555")
FAMILY_ID = UUID("66666666-6666-4666-8666-666666666666")
ACCESS_JTI = UUID("77777777-7777-4777-8777-777777777777")
AUDIT_ID_1 = UUID("88888888-8888-4888-8888-888888888881")
AUDIT_ID_2 = UUID("88888888-8888-4888-8888-888888888882")
REPLACEMENT_TOKEN_ID = UUID("55555555-5555-4555-8555-666666666666")
SECOND_ACCESS_JTI = UUID("77777777-7777-4777-8777-888888888888")
DIGEST_1 = "a" * 64
DIGEST_2 = "b" * 64


@pytest.mark.integration
async def test_login_session_creation_and_audit_commit_together() -> None:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    try:
        await SqlAlchemyUserRepository(session).add(_user(USER_ID))
        await session.commit()

        transaction = SpyTransactionManager(session)
        use_case = StartUserSession(
            authenticate_user=FakeAuthenticateUser(USER_ID),
            sessions=SqlAlchemySessionRepository(session),
            access_tokens=FakeAccessTokenCodec(),
            refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
            refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
            transaction=transaction,
            clock=FakeClock(NOW),
            ids=FakeIdGenerator(
                [SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI, AUDIT_ID_1, AUDIT_ID_2]
            ),
            audit=SqlAlchemyAuditRepository(session),
            policy=SessionLifecyclePolicy(),
        )

        await use_case(StartUserSessionCommand("ada@example.com", "password"))

        assert transaction.commits == 1
        assert transaction.rollbacks == 0
        assert await _row_count(session, AuthSessionRecord) == 1
        assert await _audit_count(session, AuditEventType.AUTHENTICATION_LOGIN_SUCCEEDED) == 1
        assert await _audit_count(session, AuditEventType.SESSION_CREATED) == 1
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_success_audit_failure_rolls_back_login_business_state() -> None:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    try:
        await SqlAlchemyUserRepository(session).add(_user(USER_ID))
        await session.commit()

        transaction = SpyTransactionManager(session)
        use_case = StartUserSession(
            authenticate_user=FakeAuthenticateUser(USER_ID),
            sessions=SqlAlchemySessionRepository(session),
            access_tokens=FakeAccessTokenCodec(),
            refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
            refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
            transaction=transaction,
            clock=FakeClock(NOW),
            ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI, AUDIT_ID_1]),
            audit=FailingAuditRecorder(),
            policy=SessionLifecyclePolicy(),
        )

        with pytest.raises(AuditPersistenceError):
            await use_case(StartUserSessionCommand("ada@example.com", "password"))

        assert transaction.commits == 0
        assert transaction.rollbacks == 1
        assert await _row_count(session, AuthSessionRecord) == 0
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_business_failure_leaves_no_success_audit() -> None:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    try:
        use_case = StartUserSession(
            authenticate_user=FakeAuthenticateUser(MISSING_USER_ID),
            sessions=SqlAlchemySessionRepository(session),
            access_tokens=FakeAccessTokenCodec(),
            refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
            refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
            transaction=SqlAlchemyTransactionManager(session),
            clock=FakeClock(NOW),
            ids=FakeIdGenerator(
                [SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI, AUDIT_ID_1, AUDIT_ID_2]
            ),
            audit=SqlAlchemyAuditRepository(session),
            policy=SessionLifecyclePolicy(),
        )

        with pytest.raises(MissingIdentityReferenceError):
            await use_case(StartUserSessionCommand("ada@example.com", "password"))

        assert await _row_count(session, AuthSessionRecord) == 0
        assert await _row_count(session, SecurityAuditEventRecord) == 0
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_refresh_rotation_and_audit_commit_together_and_rollback_together() -> None:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session_factory = create_async_session_factory(engine)
    setup = session_factory()
    try:
        await _seed_user_session_and_token(setup)
        await setup.commit()
    finally:
        await setup.close()

    success = session_factory()
    try:
        refresh = _refresh_use_case(success, audit=SqlAlchemyAuditRepository(success))
        await refresh(RefreshSessionCommand("refresh-1"))

        assert await _audit_count(success, AuditEventType.SESSION_REFRESHED) == 1
        old_token = await success.get(RefreshTokenRecordModel, TOKEN_ID)
        assert old_token is not None
        assert old_token.used_at == NOW
    finally:
        await success.close()

    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    setup = session_factory()
    try:
        await _seed_user_session_and_token(setup)
        await setup.commit()
    finally:
        await setup.close()

    failure = session_factory()
    try:
        refresh = _refresh_use_case(failure, audit=FailingAuditRecorder())
        with pytest.raises(AuditPersistenceError):
            await refresh(RefreshSessionCommand("refresh-1"))

        old_token = await failure.get(RefreshTokenRecordModel, TOKEN_ID)
        assert old_token is not None
        assert old_token.used_at is None
        assert await failure.get(RefreshTokenRecordModel, REPLACEMENT_TOKEN_ID) is None
    finally:
        await failure.close()
        await dispose_async_engine(engine)


class SpyTransactionManager(SqlAlchemyTransactionManager):
    def __init__(self, session: object) -> None:
        super().__init__(session)  # type: ignore[arg-type]
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        await super().commit()

    async def rollback(self) -> None:
        self.rollbacks += 1
        await super().rollback()


class FailingAuditRecorder:
    async def record(self, event: AuditEvent) -> None:
        raise AuditPersistenceError("audit failed")


class FakeAuthenticateUser:
    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id

    async def __call__(self, command: object) -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=self._user_id,
            email="ada@example.com",
            display_name="Ada Lovelace",
            is_active=True,
        )


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class FakeIdGenerator:
    def __init__(self, values: list[UUID]) -> None:
        self._values = list(values)

    def new_uuid(self) -> UUID:
        return self._values.pop(0)


class FakeRefreshTokenGenerator:
    def __init__(self, values: list[str]) -> None:
        self._values = list(values)

    def generate(self) -> IssuedRefreshToken:
        return IssuedRefreshToken(self._values.pop(0))


class FakeRefreshTokenHasher:
    def __init__(self, digests: dict[str, str]) -> None:
        self._digests = digests

    def digest_token(self, plain_token: str) -> RefreshTokenDigest:
        return RefreshTokenDigest(self._digests[plain_token])

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        return self.digest_token(plain_token) == token_digest


class FakeAccessTokenCodec:
    def issue_token(self, claims: AccessTokenClaims) -> str:
        return f"access:{claims.token_id}"

    def verify_token(self, token: str) -> AccessTokenClaims:
        raise AssertionError("Not used.")


async def _seed_user_session_and_token(session: object) -> None:
    users = SqlAlchemyUserRepository(session)  # type: ignore[arg-type]
    sessions = SqlAlchemySessionRepository(session)  # type: ignore[arg-type]
    await users.add(_user(USER_ID))
    await sessions.add(
        session=AuthSession.create(
            id=SessionId(SESSION_ID),
            user_id=USER_ID,
            now=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        ),
        refresh_token=RefreshTokenRecord(
            id=RefreshTokenId(TOKEN_ID),
            session_id=SessionId(SESSION_ID),
            token_family_id=RefreshTokenFamilyId(FAMILY_ID),
            token_digest=RefreshTokenDigest(DIGEST_1),
            generation=0,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        ),
    )


def _refresh_use_case(session: object, *, audit: object) -> RefreshSession:
    return RefreshSession(
        sessions=SqlAlchemySessionRepository(session),  # type: ignore[arg-type]
        access_tokens=FakeAccessTokenCodec(),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-2"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1, "refresh-2": DIGEST_2}),
        transaction=SqlAlchemyTransactionManager(session),  # type: ignore[arg-type]
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([REPLACEMENT_TOKEN_ID, SECOND_ACCESS_JTI, AUDIT_ID_1]),
        audit=audit,  # type: ignore[arg-type]
        policy=SessionLifecyclePolicy(),
    )


async def _row_count(session: object, model: type[object]) -> int:
    result = await session.execute(select(func.count()).select_from(model))  # type: ignore[attr-defined]
    return int(result.scalar_one())


async def _audit_count(session: object, event_type: AuditEventType) -> int:
    result = await session.execute(  # type: ignore[attr-defined]
        select(func.count())
        .select_from(SecurityAuditEventRecord)
        .where(SecurityAuditEventRecord.event_type == event_type.value)
    )
    return int(result.scalar_one())


def _user(user_id: UUID) -> User:
    return User.create(
        id=user_id,
        email=EmailAddress("ada@example.com"),
        display_name="Ada Lovelace",
        now=NOW,
    )


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

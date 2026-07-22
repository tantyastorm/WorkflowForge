"""Session lifecycle transaction integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from workflowforge_application.identity import (
    AccessTokenClaims,
    IssuedRefreshToken,
    RefreshSession,
    RefreshSessionCommand,
    RefreshTokenReplayError,
    SessionLifecyclePolicy,
)
from workflowforge_domain.audit import AuditEventType
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

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
REPLAYED_AT = NOW + timedelta(minutes=10)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
SECOND_SESSION_ID = UUID("44444444-4444-4444-8444-555555555555")
TOKEN_ID = UUID("55555555-5555-4555-8555-555555555555")
REPLACEMENT_TOKEN_ID = UUID("55555555-5555-4555-8555-666666666666")
SECOND_TOKEN_ID = UUID("55555555-5555-4555-8555-777777777777")
FAMILY_ID = UUID("66666666-6666-4666-8666-666666666666")
SECOND_FAMILY_ID = UUID("66666666-6666-4666-8666-777777777777")
ACCESS_JTI = UUID("77777777-7777-4777-8777-777777777777")
DIGEST = "a" * 64
REPLACEMENT_DIGEST = "b" * 64
SECOND_DIGEST = "c" * 64


@pytest.mark.integration
async def test_refresh_replay_revocation_commits_before_error_is_returned() -> None:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session_factory = create_async_session_factory(engine)
    setup_session = session_factory()

    try:
        user_repo = SqlAlchemyUserRepository(setup_session)
        session_repo = SqlAlchemySessionRepository(setup_session)
        await user_repo.add(_user())
        await session_repo.add(session=_auth_session(), refresh_token=_refresh_token())
        await session_repo.rotate_refresh_token(
            session_id=SessionId(SESSION_ID),
            expected_digest=RefreshTokenDigest(DIGEST),
            expected_generation=0,
            replacement=_refresh_token(
                token_id=REPLACEMENT_TOKEN_ID,
                digest=REPLACEMENT_DIGEST,
                generation=1,
                issued_at=NOW + timedelta(minutes=5),
            ),
            rotated_at=NOW + timedelta(minutes=5),
        )
        await session_repo.add(
            session=_auth_session(session_id=SECOND_SESSION_ID),
            refresh_token=_refresh_token(
                token_id=SECOND_TOKEN_ID,
                session_id=SECOND_SESSION_ID,
                family_id=SECOND_FAMILY_ID,
                digest=SECOND_DIGEST,
            ),
        )
        await setup_session.commit()

        use_case_session = session_factory()
        try:
            replay = RefreshSession(
                sessions=SqlAlchemySessionRepository(use_case_session),
                access_tokens=FakeAccessTokenCodec(),
                refresh_tokens=FakeRefreshTokenGenerator(),
                refresh_token_hasher=FakeRefreshTokenHasher({"old-refresh": DIGEST}),
                transaction=SqlAlchemyTransactionManager(use_case_session),
                clock=FakeClock(REPLAYED_AT),
                ids=FakeIdGenerator(),
                audit=SqlAlchemyAuditRepository(use_case_session),
                policy=SessionLifecyclePolicy(),
            )

            with pytest.raises(RefreshTokenReplayError):
                await replay(RefreshSessionCommand("old-refresh"))
        finally:
            await use_case_session.close()

        verifier_session = session_factory()
        try:
            verifier = SqlAlchemySessionRepository(verifier_session)
            revoked = await verifier.get_by_id(SessionId(SESSION_ID))
            current_token = await verifier.get_refresh_token_by_digest(
                RefreshTokenDigest(REPLACEMENT_DIGEST)
            )
            other_session = await verifier.get_active_by_id(
                SessionId(SECOND_SESSION_ID),
                at=REPLAYED_AT,
            )
            other_token = await verifier.get_refresh_token_by_digest(
                RefreshTokenDigest(SECOND_DIGEST)
            )

            assert revoked is not None
            assert revoked.revoked_at == REPLAYED_AT
            assert current_token is not None
            assert current_token.revoked_at == REPLAYED_AT
            assert other_session is not None
            assert other_token is not None
            assert other_token.revoked_at is None
            assert (
                await _audit_count(
                    verifier_session,
                    AuditEventType.SESSION_REFRESH_REPLAY_DETECTED,
                )
                == 1
            )
            assert await _audit_count(verifier_session, AuditEventType.SESSION_REVOKED) == 1
        finally:
            await verifier_session.close()
    finally:
        await setup_session.close()
        await dispose_async_engine(engine)


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class FakeIdGenerator:
    def __init__(self) -> None:
        self._values = [
            ACCESS_JTI,
            UUID("88888888-8888-4888-8888-888888888881"),
        ]

    def new_uuid(self) -> UUID:
        return self._values.pop(0)


class FakeRefreshTokenGenerator:
    def generate(self) -> IssuedRefreshToken:
        return IssuedRefreshToken("unused-refresh")


class FakeRefreshTokenHasher:
    def __init__(self, digests: dict[str, str]) -> None:
        self._digests = digests

    def digest_token(self, plain_token: str) -> RefreshTokenDigest:
        return RefreshTokenDigest(self._digests.get(plain_token, "f" * 64))

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        return self.digest_token(plain_token) == token_digest


class FakeAccessTokenCodec:
    def issue_token(self, claims: AccessTokenClaims) -> str:
        return f"access:{claims.token_id}"

    def verify_token(self, token: str) -> AccessTokenClaims:
        raise AssertionError("Replay test does not verify access tokens.")


def _user() -> User:
    return User.create(
        id=USER_ID,
        email=EmailAddress("ada@example.com"),
        display_name="Ada Lovelace",
        now=NOW,
    )


def _auth_session(
    *,
    session_id: UUID = SESSION_ID,
) -> AuthSession:
    return AuthSession.create(
        id=SessionId(session_id),
        user_id=USER_ID,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _refresh_token(
    *,
    token_id: UUID = TOKEN_ID,
    session_id: UUID = SESSION_ID,
    family_id: UUID = FAMILY_ID,
    digest: str = DIGEST,
    generation: int = 0,
    issued_at: datetime = NOW,
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(token_id),
        session_id=SessionId(session_id),
        token_family_id=RefreshTokenFamilyId(family_id),
        token_digest=RefreshTokenDigest(digest),
        generation=generation,
        issued_at=issued_at,
        expires_at=NOW + timedelta(hours=1),
    )


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config


async def _audit_count(session: object, event_type: AuditEventType) -> int:
    result = await session.execute(  # type: ignore[attr-defined]
        select(func.count())
        .select_from(SecurityAuditEventRecord)
        .where(SecurityAuditEventRecord.event_type == event_type.value)
    )
    return int(result.scalar_one())

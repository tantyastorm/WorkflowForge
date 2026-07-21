"""Authenticated session lifecycle application tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_application.identity import (
    AccessTokenClaims,
    AuthenticatedUser,
    ExpiredRefreshTokenError,
    GeneratedRefreshCredential,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    IssuedRefreshToken,
    LogoutAllSessions,
    LogoutAllSessionsCommand,
    LogoutSession,
    LogoutSessionCommand,
    RefreshRotationConflictError,
    RefreshSession,
    RefreshSessionCommand,
    RefreshTokenReplayError,
    SessionLifecyclePolicy,
    SessionNotFoundError,
    SessionOwnershipError,
    StartUserSession,
    StartUserSessionCommand,
    TokenIssuanceError,
    VerifyAccessToken,
)
from workflowforge_domain.identity import (
    AuthSession,
    RefreshTokenDigest,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    SessionId,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("11111111-1111-4111-8111-222222222222")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
SECOND_SESSION_ID = UUID("44444444-4444-4444-8444-555555555555")
TOKEN_ID = UUID("55555555-5555-4555-8555-555555555555")
REPLACEMENT_TOKEN_ID = UUID("55555555-5555-4555-8555-666666666666")
FAMILY_ID = UUID("66666666-6666-4666-8666-666666666666")
ACCESS_JTI = UUID("77777777-7777-4777-8777-777777777777")
SECOND_ACCESS_JTI = UUID("77777777-7777-4777-8777-888888888888")
DIGEST_1 = "1" * 64
DIGEST_2 = "2" * 64
POLICY = SessionLifecyclePolicy(
    access_token_lifetime=timedelta(minutes=15),
    refresh_token_lifetime=timedelta(days=30),
    session_lifetime=timedelta(days=30),
)


@pytest.mark.asyncio
async def test_start_user_session_creates_session_initial_refresh_and_token_pair() -> None:
    sessions = FakeSessionRepository()
    access_tokens = FakeAccessTokenCodec()
    transaction = FakeTransactionManager()
    use_case = StartUserSession(
        authenticate_user=FakeAuthenticateUser(),
        sessions=sessions,
        access_tokens=access_tokens,
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
        transaction=transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI]),
        policy=POLICY,
    )

    result = await use_case(StartUserSessionCommand("ada@example.com", "password"))

    session = sessions.sessions[SessionId(SESSION_ID)]
    token = sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)]
    assert session.user_id == USER_ID
    assert session.expires_at == NOW + timedelta(days=30)
    assert token.generation == 0
    assert token.token_family_id == RefreshTokenFamilyId(FAMILY_ID)
    assert token.expires_at == NOW + timedelta(days=30)
    assert result.access_token == f"access:{ACCESS_JTI}"
    assert result.refresh_token == "refresh-1"
    assert result.token_type == "Bearer"
    assert result.session_id == SessionId(SESSION_ID)
    assert result.access_token_expires_at == NOW + timedelta(minutes=15)
    assert result.refresh_token_expires_at == NOW + timedelta(days=30)
    assert "refresh-1" not in repr(result)
    assert f"access:{ACCESS_JTI}" not in repr(result)
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


def test_generated_refresh_credential_repr_redacts_raw_token() -> None:
    credential = GeneratedRefreshCredential(
        token=IssuedRefreshToken("raw-refresh-token"),
        digest=RefreshTokenDigest(DIGEST_1),
    )

    assert "raw-refresh-token" not in repr(credential)


@pytest.mark.asyncio
async def test_start_user_session_failures_do_not_persist_session() -> None:
    sessions = FakeSessionRepository()
    invalid_transaction = FakeTransactionManager()
    invalid_auth = StartUserSession(
        authenticate_user=FakeAuthenticateUser(error=InvalidCredentialsError("Invalid")),
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
        transaction=invalid_transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI]),
        policy=POLICY,
    )
    with pytest.raises(InvalidCredentialsError):
        await invalid_auth(StartUserSessionCommand("ada@example.com", "bad"))
    assert sessions.sessions == {}
    assert invalid_transaction.commits == 0
    assert invalid_transaction.rollbacks == 1

    issuance_transaction = FakeTransactionManager()
    issuance_failure = StartUserSession(
        authenticate_user=FakeAuthenticateUser(),
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(issue_error=TokenIssuanceError("No token")),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
        transaction=issuance_transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI]),
        policy=POLICY,
    )
    with pytest.raises(TokenIssuanceError):
        await issuance_failure(StartUserSessionCommand("ada@example.com", "password"))
    assert sessions.sessions == {}
    assert issuance_transaction.commits == 0
    assert issuance_transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_start_user_session_persistence_failure_returns_no_result() -> None:
    sessions = FakeSessionRepository(add_error=RuntimeError("database unavailable"))
    transaction = FakeTransactionManager()
    use_case = StartUserSession(
        authenticate_user=FakeAuthenticateUser(),
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
        transaction=transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI]),
        policy=POLICY,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await use_case(StartUserSessionCommand("ada@example.com", "password"))

    assert sessions.sessions == {}
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_start_user_session_commit_failure_returns_no_result() -> None:
    sessions = FakeSessionRepository()
    transaction = FakeTransactionManager(commit_error=RuntimeError("commit failed"))
    use_case = StartUserSession(
        authenticate_user=FakeAuthenticateUser(),
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-1"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1}),
        transaction=transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([SESSION_ID, TOKEN_ID, FAMILY_ID, ACCESS_JTI]),
        policy=POLICY,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await use_case(StartUserSessionCommand("ada@example.com", "password"))

    assert transaction.commits == 1
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_session_rotates_token_preserves_family_without_extending_session() -> None:
    sessions = FakeSessionRepository()
    session = _session(expires_at=NOW + timedelta(hours=1))
    current = _refresh_token(expires_at=NOW + timedelta(hours=1))
    await sessions.add(session=session, refresh_token=current)
    access_tokens = FakeAccessTokenCodec()
    transaction = FakeTransactionManager()
    use_case = RefreshSession(
        sessions=sessions,
        access_tokens=access_tokens,
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-2"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1, "refresh-2": DIGEST_2}),
        transaction=transaction,
        clock=FakeClock(NOW + timedelta(minutes=5)),
        ids=FakeIdGenerator([REPLACEMENT_TOKEN_ID, SECOND_ACCESS_JTI]),
        policy=POLICY,
    )

    result = await use_case(RefreshSessionCommand("refresh-1"))

    old = sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)]
    replacement = sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_2)]
    assert old.used_at == NOW + timedelta(minutes=5)
    assert old.replaced_by_token_id == RefreshTokenId(REPLACEMENT_TOKEN_ID)
    assert replacement.generation == 1
    assert replacement.token_family_id == RefreshTokenFamilyId(FAMILY_ID)
    assert replacement.expires_at == session.expires_at
    assert result.refresh_token == "refresh-2"
    assert result.access_token == f"access:{SECOND_ACCESS_JTI}"
    assert result.refresh_token_expires_at == session.expires_at
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_refresh_session_rejects_unknown_expired_revoked_and_stale_tokens() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())

    transaction = FakeTransactionManager()
    use_case = _refresh_use_case(
        sessions=sessions,
        raw_tokens=["refresh-2"],
        transaction=transaction,
    )
    with pytest.raises(InvalidRefreshTokenError):
        await use_case(RefreshSessionCommand("unknown"))
    assert transaction.commits == 0
    assert transaction.rollbacks == 1

    sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)] = _refresh_token(
        issued_at=NOW - timedelta(hours=1),
        expires_at=NOW - timedelta(seconds=1),
    )
    with pytest.raises(ExpiredRefreshTokenError):
        await use_case(RefreshSessionCommand("refresh-1"))
    assert transaction.commits == 0
    assert transaction.rollbacks == 2

    sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)] = _refresh_token(
        revoked_at=NOW,
    )
    with pytest.raises(InvalidRefreshTokenError):
        await use_case(RefreshSessionCommand("refresh-1"))
    assert transaction.commits == 0
    assert transaction.rollbacks == 3

    sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)] = _refresh_token()
    sessions.conflict_on_rotate = True
    with pytest.raises(RefreshRotationConflictError):
        await use_case(RefreshSessionCommand("refresh-1"))
    assert transaction.commits == 0
    assert transaction.rollbacks == 4


@pytest.mark.asyncio
async def test_refresh_session_issuance_failure_does_not_consume_token() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())
    transaction = FakeTransactionManager()
    use_case = RefreshSession(
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(issue_error=TokenIssuanceError("No token")),
        refresh_tokens=FakeRefreshTokenGenerator(["refresh-2"]),
        refresh_token_hasher=FakeRefreshTokenHasher({"refresh-1": DIGEST_1, "refresh-2": DIGEST_2}),
        transaction=transaction,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([REPLACEMENT_TOKEN_ID, SECOND_ACCESS_JTI]),
        policy=POLICY,
    )

    with pytest.raises(TokenIssuanceError):
        await use_case(RefreshSessionCommand("refresh-1"))

    current = sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)]
    assert current.used_at is None
    assert current.replaced_by_token_id is None
    assert RefreshTokenDigest(DIGEST_2) not in sessions.tokens_by_digest
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_session_rotation_failure_returns_no_tokens() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())
    sessions.conflict_on_rotate = True
    transaction = FakeTransactionManager()
    use_case = _refresh_use_case(
        sessions=sessions,
        raw_tokens=["refresh-2"],
        transaction=transaction,
    )

    with pytest.raises(RefreshRotationConflictError):
        await use_case(RefreshSessionCommand("refresh-1"))

    current = sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)]
    assert current.used_at is None
    assert current.replaced_by_token_id is None
    assert RefreshTokenDigest(DIGEST_2) not in sessions.tokens_by_digest
    assert transaction.commits == 0
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_session_commit_failure_returns_no_tokens() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())
    transaction = FakeTransactionManager(commit_error=RuntimeError("commit failed"))
    use_case = _refresh_use_case(
        sessions=sessions,
        raw_tokens=["refresh-2"],
        transaction=transaction,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await use_case(RefreshSessionCommand("refresh-1"))

    assert transaction.commits == 1
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_replay_revokes_session_and_descendant_token() -> None:
    sessions = FakeSessionRepository()
    session = _session()
    used = _refresh_token(
        issued_at=NOW - timedelta(minutes=2),
        used_at=NOW - timedelta(minutes=1),
        replaced_by_token_id=RefreshTokenId(REPLACEMENT_TOKEN_ID),
    )
    descendant = _refresh_token(
        token_id=REPLACEMENT_TOKEN_ID,
        digest=DIGEST_2,
        generation=1,
    )
    await sessions.add(session=session, refresh_token=used)
    sessions.tokens_by_digest[descendant.token_digest] = descendant

    transaction = FakeTransactionManager()
    use_case = _refresh_use_case(
        sessions=sessions,
        raw_tokens=["refresh-3"],
        transaction=transaction,
    )
    with pytest.raises(RefreshTokenReplayError):
        await use_case(RefreshSessionCommand("refresh-1"))

    assert sessions.sessions[SessionId(SESSION_ID)].revoked_at == NOW
    assert sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_2)].revoked_at == NOW
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    with pytest.raises(InvalidRefreshTokenError):
        await use_case(RefreshSessionCommand("refresh-2"))
    assert transaction.commits == 1
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_logout_one_requires_ownership_and_is_idempotent() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())
    transaction = FakeTransactionManager()
    use_case = LogoutSession(sessions=sessions, transaction=transaction, clock=FakeClock(NOW))

    await use_case(LogoutSessionCommand(user_id=USER_ID, session_id=SessionId(SESSION_ID)))
    await use_case(LogoutSessionCommand(user_id=USER_ID, session_id=SessionId(SESSION_ID)))

    assert sessions.sessions[SessionId(SESSION_ID)].revoked_at == NOW
    assert sessions.tokens_by_digest[RefreshTokenDigest(DIGEST_1)].revoked_at == NOW
    assert transaction.commits == 2
    assert transaction.rollbacks == 0

    with pytest.raises(SessionOwnershipError):
        await use_case(LogoutSessionCommand(OTHER_USER_ID, SessionId(SESSION_ID)))
    with pytest.raises(SessionNotFoundError):
        await use_case(LogoutSessionCommand(USER_ID, SessionId(SECOND_SESSION_ID)))
    assert transaction.commits == 2
    assert transaction.rollbacks == 2


@pytest.mark.asyncio
async def test_logout_all_revokes_only_one_users_sessions() -> None:
    sessions = FakeSessionRepository()
    await sessions.add(session=_session(), refresh_token=_refresh_token())
    await sessions.add(
        session=_session(session_id=SECOND_SESSION_ID, user_id=OTHER_USER_ID),
        refresh_token=_refresh_token(
            token_id=REPLACEMENT_TOKEN_ID,
            session_id=SECOND_SESSION_ID,
            digest=DIGEST_2,
        ),
    )
    transaction = FakeTransactionManager()
    use_case = LogoutAllSessions(
        sessions=sessions,
        transaction=transaction,
        clock=FakeClock(NOW),
    )

    result = await use_case(LogoutAllSessionsCommand(USER_ID))

    assert result.revoked_sessions == 1
    assert sessions.sessions[SessionId(SESSION_ID)].revoked_at == NOW
    assert sessions.sessions[SessionId(SECOND_SESSION_ID)].revoked_at is None
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_verify_access_token_requires_active_matching_session() -> None:
    sessions = FakeSessionRepository()
    session = _session()
    await sessions.add(session=session, refresh_token=_refresh_token())
    claims = AccessTokenClaims(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=ACCESS_JTI,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    access_tokens = FakeAccessTokenCodec(verified_claims={"token": claims})
    use_case = VerifyAccessToken(
        sessions=sessions,
        access_tokens=access_tokens,
        clock=FakeClock(NOW),
    )

    principal = await use_case("token")

    assert principal.user_id == USER_ID
    assert principal.session_id == SessionId(SESSION_ID)
    assert principal.token_id == ACCESS_JTI

    await sessions.revoke(SessionId(SESSION_ID), revoked_at=NOW)
    with pytest.raises(InvalidAccessTokenError):
        await use_case("token")


@pytest.mark.asyncio
async def test_verify_access_token_rejects_missing_and_mismatched_session() -> None:
    sessions = FakeSessionRepository()
    claims = AccessTokenClaims(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=ACCESS_JTI,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    use_case = VerifyAccessToken(
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(verified_claims={"token": claims}),
        clock=FakeClock(NOW),
    )
    with pytest.raises(InvalidAccessTokenError):
        await use_case("token")

    await sessions.add(
        session=_session(user_id=OTHER_USER_ID),
        refresh_token=_refresh_token(),
    )
    with pytest.raises(InvalidAccessTokenError):
        await use_case("token")


class FakeAuthenticateUser:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def __call__(self, command: object) -> AuthenticatedUser:
        if self._error is not None:
            raise self._error
        return AuthenticatedUser(
            user_id=USER_ID,
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
        return RefreshTokenDigest(self._digests.get(plain_token, "f" * 64))

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        return self.digest_token(plain_token) == token_digest


class FakeAccessTokenCodec:
    def __init__(
        self,
        *,
        issue_error: Exception | None = None,
        verified_claims: dict[str, AccessTokenClaims] | None = None,
    ) -> None:
        self._issue_error = issue_error
        self._verified_claims = verified_claims or {}

    def issue_token(self, claims: AccessTokenClaims) -> str:
        if self._issue_error is not None:
            raise self._issue_error
        return f"access:{claims.token_id}"

    def verify_token(self, token: str) -> AccessTokenClaims:
        try:
            return self._verified_claims[token]
        except KeyError as exc:
            raise InvalidAccessTokenError("Invalid") from exc


class FakeTransactionManager:
    def __init__(
        self,
        *,
        commit_error: Exception | None = None,
        rollback_error: Exception | None = None,
    ) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.events: list[str] = []
        self._commit_error = commit_error
        self._rollback_error = rollback_error

    async def commit(self) -> None:
        self.commits += 1
        self.events.append("commit")
        if self._commit_error is not None:
            raise self._commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.events.append("rollback")
        if self._rollback_error is not None:
            raise self._rollback_error


class FakeSessionRepository:
    def __init__(self, add_error: Exception | None = None) -> None:
        self.sessions: dict[SessionId, AuthSession] = {}
        self.tokens_by_digest: dict[RefreshTokenDigest, RefreshTokenRecord] = {}
        self._add_error = add_error
        self.conflict_on_rotate = False

    async def add(
        self,
        *,
        session: AuthSession,
        refresh_token: RefreshTokenRecord,
    ) -> AuthSession:
        if self._add_error is not None:
            raise self._add_error
        self.sessions[session.id] = session
        self.tokens_by_digest[refresh_token.token_digest] = refresh_token
        return session

    async def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        return self.sessions.get(session_id)

    async def get_active_by_id(
        self,
        session_id: SessionId,
        *,
        at: datetime,
    ) -> AuthSession | None:
        session = self.sessions.get(session_id)
        if session is None or not session.is_active(at):
            return None
        return session

    async def get_refresh_token_by_digest(
        self,
        token_digest: RefreshTokenDigest,
    ) -> RefreshTokenRecord | None:
        return self.tokens_by_digest.get(token_digest)

    async def update(self, session: AuthSession) -> AuthSession:
        self.sessions[session.id] = session
        return session

    async def revoke(self, session_id: SessionId, *, revoked_at: datetime) -> AuthSession:
        session = self.sessions[session_id].revoke(now=revoked_at)
        self.sessions[session_id] = session
        for digest, token in list(self.tokens_by_digest.items()):
            if (
                token.session_id == session_id
                and token.used_at is None
                and token.revoked_at is None
            ):
                self.tokens_by_digest[digest] = token.revoke(now=revoked_at)
        return session

    async def revoke_all_for_user(self, user_id: UUID, *, revoked_at: datetime) -> int:
        count = 0
        for session in list(self.sessions.values()):
            if session.user_id == user_id and session.revoked_at is None:
                await self.revoke(session.id, revoked_at=revoked_at)
                count += 1
        return count

    async def rotate_refresh_token(
        self,
        *,
        session_id: SessionId,
        expected_digest: RefreshTokenDigest,
        expected_generation: int,
        replacement: RefreshTokenRecord,
        rotated_at: datetime,
    ) -> RefreshTokenRecord:
        if self.conflict_on_rotate:
            raise RefreshRotationConflictError("Conflict")
        current = self.tokens_by_digest[expected_digest]
        if (
            current.session_id != session_id
            or current.generation != expected_generation
            or not current.is_current(rotated_at)
        ):
            raise RefreshRotationConflictError("Conflict")
        self.tokens_by_digest[expected_digest] = current.consume(
            replacement_token_id=replacement.id,
            now=rotated_at,
        )
        self.tokens_by_digest[replacement.token_digest] = replacement
        return replacement


def _session(
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    expires_at: datetime = NOW + timedelta(days=30),
) -> AuthSession:
    return AuthSession.create(
        id=SessionId(session_id),
        user_id=user_id,
        now=NOW,
        expires_at=expires_at,
    )


def _refresh_token(
    *,
    token_id: UUID = TOKEN_ID,
    session_id: UUID = SESSION_ID,
    family_id: UUID = FAMILY_ID,
    digest: str = DIGEST_1,
    generation: int = 0,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(days=30),
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
    replaced_by_token_id: RefreshTokenId | None = None,
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(token_id),
        session_id=SessionId(session_id),
        token_family_id=RefreshTokenFamilyId(family_id),
        token_digest=RefreshTokenDigest(digest),
        generation=generation,
        issued_at=issued_at,
        expires_at=expires_at,
        used_at=used_at,
        revoked_at=revoked_at,
        replaced_by_token_id=replaced_by_token_id,
    )


def _refresh_use_case(
    *,
    sessions: FakeSessionRepository,
    raw_tokens: list[str],
    transaction: FakeTransactionManager | None = None,
) -> RefreshSession:
    return RefreshSession(
        sessions=sessions,
        access_tokens=FakeAccessTokenCodec(),
        refresh_tokens=FakeRefreshTokenGenerator(raw_tokens),
        refresh_token_hasher=FakeRefreshTokenHasher(
            {
                "refresh-1": DIGEST_1,
                "refresh-2": DIGEST_2,
                "refresh-3": "3" * 64,
            }
        ),
        transaction=transaction or FakeTransactionManager(),
        clock=FakeClock(NOW),
        ids=FakeIdGenerator([REPLACEMENT_TOKEN_ID, SECOND_ACCESS_JTI]),
        policy=POLICY,
    )

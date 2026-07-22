"""Authenticated session lifecycle use cases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from workflowforge_domain.audit import (
    AuditEvent,
    AuditEventType,
    AuditOutcome,
    AuditRequestContext,
)
from workflowforge_domain.identity import (
    AuthSession,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    SessionId,
)

from workflowforge_application.audit import AuditRecorder
from workflowforge_application.identity.authentication import (
    AuthenticatedUser,
    AuthenticateUserCommand,
)
from workflowforge_application.identity.errors import (
    ExpiredAccessTokenError,
    ExpiredRefreshTokenError,
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
    RefreshTokenReplayError,
    SessionNotFoundError,
    SessionOwnershipError,
)
from workflowforge_application.identity.ports import (
    AccessTokenCodec,
    Clock,
    IdGenerator,
    RefreshTokenGenerator,
    RefreshTokenHasher,
    SessionRepository,
    TransactionManager,
)
from workflowforge_application.identity.tokens import (
    AccessTokenClaims,
    GeneratedRefreshCredential,
    TokenPair,
    VerifiedAccessPrincipal,
)

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
SESSION_LIFETIME = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class SessionLifecyclePolicy:
    """Durations used by session lifecycle use cases."""

    access_token_lifetime: timedelta = ACCESS_TOKEN_LIFETIME
    refresh_token_lifetime: timedelta = REFRESH_TOKEN_LIFETIME
    session_lifetime: timedelta = SESSION_LIFETIME

    def __post_init__(self) -> None:
        for field_name in (
            "access_token_lifetime",
            "refresh_token_lifetime",
            "session_lifetime",
        ):
            value = getattr(self, field_name)
            if value <= timedelta(0):
                msg = f"{field_name} must be positive."
                raise ValueError(msg)
        if self.refresh_token_lifetime > self.session_lifetime:
            msg = "refresh_token_lifetime must not exceed session_lifetime."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class StartUserSessionCommand:
    """Input for starting an authenticated session."""

    email: str
    password: str
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class RefreshSessionCommand:
    """Input for refresh-token rotation."""

    refresh_token: str
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class LogoutSessionCommand:
    """Input for revoking one owned session."""

    user_id: UUID
    session_id: SessionId
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class LogoutAllSessionsCommand:
    """Input for revoking all sessions for a user."""

    user_id: UUID
    session_id: SessionId | None = None
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class LogoutAllSessionsResult:
    """Result of logout-all."""

    revoked_sessions: int


class StartUserSession:
    """Authenticate a user and create a durable session plus token pair."""

    def __init__(
        self,
        *,
        authenticate_user: Callable[[AuthenticateUserCommand], Awaitable[AuthenticatedUser]],
        sessions: SessionRepository,
        access_tokens: AccessTokenCodec,
        refresh_tokens: RefreshTokenGenerator,
        refresh_token_hasher: RefreshTokenHasher,
        transaction: TransactionManager,
        clock: Clock,
        ids: IdGenerator,
        audit: AuditRecorder | None = None,
        policy: SessionLifecyclePolicy | None = None,
    ) -> None:
        self._authenticate_user = authenticate_user
        self._sessions = sessions
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._refresh_token_hasher = refresh_token_hasher
        self._transaction = transaction
        self._clock = clock
        self._ids = ids
        self._audit = audit
        self._policy = policy or SessionLifecyclePolicy()

    async def __call__(self, command: StartUserSessionCommand) -> TokenPair:
        """Return a token pair for valid credentials."""

        try:
            user = await self._authenticate_user(
                AuthenticateUserCommand(email=command.email, password=command.password)
            )
            issued_at = _normalize_timestamp(self._clock.now())
            session_id = SessionId(self._ids.new_uuid())
            session_expires_at = issued_at + self._policy.session_lifetime
            refresh_expires_at = issued_at + self._policy.refresh_token_lifetime
            session = AuthSession.create(
                id=session_id,
                user_id=user.user_id,
                now=issued_at,
                expires_at=session_expires_at,
            )
            refresh_credential = self._new_refresh_credential()
            refresh_record = RefreshTokenRecord.issue_initial(
                id=RefreshTokenId(self._ids.new_uuid()),
                session_id=session_id,
                token_family_id=RefreshTokenFamilyId(self._ids.new_uuid()),
                token_digest=refresh_credential.digest,
                issued_at=issued_at,
                expires_at=refresh_expires_at,
            )
            access_token, access_expires_at = self._issue_access_token(
                user_id=user.user_id,
                session_id=session_id,
                issued_at=issued_at,
            )
            await self._sessions.add(session=session, refresh_token=refresh_record)
            if self._audit is not None:
                await self._audit.record(
                    AuditEvent.create(
                        id=self._ids.new_uuid(),
                        event_type=AuditEventType.AUTHENTICATION_LOGIN_SUCCEEDED,
                        outcome=AuditOutcome.SUCCESS,
                        occurred_at=issued_at,
                        actor_user_id=user.user_id,
                        session_id=session_id.value,
                        request_context=command.audit_context,
                    )
                )
                await self._audit.record(
                    AuditEvent.create(
                        id=self._ids.new_uuid(),
                        event_type=AuditEventType.SESSION_CREATED,
                        outcome=AuditOutcome.SUCCESS,
                        occurred_at=issued_at,
                        actor_user_id=user.user_id,
                        session_id=session_id.value,
                        request_context=command.audit_context,
                    )
                )
            await self._transaction.commit()
            return TokenPair(
                access_token=access_token,
                refresh_token=refresh_credential.token.value,
                token_type="Bearer",
                session_id=session_id,
                access_token_expires_at=access_expires_at,
                refresh_token_expires_at=refresh_expires_at,
            )
        except Exception:
            await self._transaction.rollback()
            raise

    def _new_refresh_credential(self) -> GeneratedRefreshCredential:
        token = self._refresh_tokens.generate()
        return GeneratedRefreshCredential(
            token=token,
            digest=self._refresh_token_hasher.digest_token(token.value),
        )

    def _issue_access_token(
        self,
        *,
        user_id: UUID,
        session_id: SessionId,
        issued_at: datetime,
    ) -> tuple[str, datetime]:
        expires_at = issued_at + self._policy.access_token_lifetime
        claims = AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            token_id=self._ids.new_uuid(),
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return self._access_tokens.issue_token(claims), expires_at


class RefreshSession:
    """Rotate a refresh token and return a replacement token pair."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        access_tokens: AccessTokenCodec,
        refresh_tokens: RefreshTokenGenerator,
        refresh_token_hasher: RefreshTokenHasher,
        transaction: TransactionManager,
        clock: Clock,
        ids: IdGenerator,
        audit: AuditRecorder | None = None,
        policy: SessionLifecyclePolicy | None = None,
    ) -> None:
        self._sessions = sessions
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._refresh_token_hasher = refresh_token_hasher
        self._transaction = transaction
        self._clock = clock
        self._ids = ids
        self._audit = audit
        self._policy = policy or SessionLifecyclePolicy()

    async def __call__(self, command: RefreshSessionCommand) -> TokenPair:
        """Rotate a current refresh token."""

        try:
            rotated_at = _normalize_timestamp(self._clock.now())
            digest = self._refresh_token_hasher.digest_token(command.refresh_token)
            current = await self._sessions.get_refresh_token_by_digest(digest)
            if current is None:
                msg = "Refresh token is invalid."
                raise InvalidRefreshTokenError(msg)
            if current.used_at is not None or current.replaced_by_token_id is not None:
                await self._sessions.revoke(current.session_id, revoked_at=rotated_at)
                if self._audit is not None:
                    await self._audit.record(
                        AuditEvent.create(
                            id=self._ids.new_uuid(),
                            event_type=AuditEventType.SESSION_REFRESH_REPLAY_DETECTED,
                            outcome=AuditOutcome.REPLAY_DETECTED,
                            occurred_at=rotated_at,
                            session_id=current.session_id.value,
                            request_context=command.audit_context,
                        )
                    )
                    await self._audit.record(
                        AuditEvent.create(
                            id=self._ids.new_uuid(),
                            event_type=AuditEventType.SESSION_REVOKED,
                            outcome=AuditOutcome.SUCCESS,
                            occurred_at=rotated_at,
                            session_id=current.session_id.value,
                            request_context=command.audit_context,
                            metadata={"reason": "refresh_replay"},
                        )
                    )
                await self._transaction.commit()
                msg = "Refresh token replay was detected."
                raise RefreshTokenReplayError(msg)
            if current.revoked_at is not None:
                msg = "Refresh token is invalid."
                raise InvalidRefreshTokenError(msg)
            if current.is_expired(rotated_at):
                msg = "Refresh token has expired."
                raise ExpiredRefreshTokenError(msg)

            session = await self._sessions.get_active_by_id(current.session_id, at=rotated_at)
            if session is None:
                msg = "Refresh token is invalid."
                raise InvalidRefreshTokenError(msg)

            refresh_credential = self._new_refresh_credential()
            replacement = current.replacement(
                id=RefreshTokenId(self._ids.new_uuid()),
                token_digest=refresh_credential.digest,
                issued_at=rotated_at,
                expires_at=min(
                    rotated_at + self._policy.refresh_token_lifetime,
                    session.expires_at,
                ),
            )
            access_token, access_expires_at = self._issue_access_token(
                user_id=session.user_id,
                session_id=session.id,
                issued_at=rotated_at,
            )
            await self._sessions.rotate_refresh_token(
                session_id=session.id,
                expected_digest=digest,
                expected_generation=current.generation,
                replacement=replacement,
                rotated_at=rotated_at,
            )
            if self._audit is not None:
                await self._audit.record(
                    AuditEvent.create(
                        id=self._ids.new_uuid(),
                        event_type=AuditEventType.SESSION_REFRESHED,
                        outcome=AuditOutcome.SUCCESS,
                        occurred_at=rotated_at,
                        actor_user_id=session.user_id,
                        session_id=session.id.value,
                        request_context=command.audit_context,
                    )
                )
            await self._transaction.commit()
        except RefreshTokenReplayError:
            raise
        except Exception:
            await self._transaction.rollback()
            raise
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_credential.token.value,
            token_type="Bearer",
            session_id=session.id,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=replacement.expires_at,
        )

    def _new_refresh_credential(self) -> GeneratedRefreshCredential:
        token = self._refresh_tokens.generate()
        return GeneratedRefreshCredential(
            token=token,
            digest=self._refresh_token_hasher.digest_token(token.value),
        )

    def _issue_access_token(
        self,
        *,
        user_id: UUID,
        session_id: SessionId,
        issued_at: datetime,
    ) -> tuple[str, datetime]:
        expires_at = issued_at + self._policy.access_token_lifetime
        claims = AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            token_id=self._ids.new_uuid(),
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return self._access_tokens.issue_token(claims), expires_at


class LogoutSession:
    """Revoke one session after checking ownership."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        transaction: TransactionManager,
        clock: Clock,
        ids: IdGenerator | None = None,
        audit: AuditRecorder | None = None,
    ) -> None:
        self._sessions = sessions
        self._transaction = transaction
        self._clock = clock
        self._ids = ids
        self._audit = audit

    async def __call__(self, command: LogoutSessionCommand) -> None:
        """Revoke one owned session."""

        try:
            session = await self._sessions.get_by_id(command.session_id)
            if session is None:
                msg = "Session does not exist."
                raise SessionNotFoundError(msg)
            if session.user_id != command.user_id:
                msg = "Session does not belong to the user."
                raise SessionOwnershipError(msg)
            revoked_at = _normalize_timestamp(self._clock.now())
            await self._sessions.revoke(
                command.session_id,
                revoked_at=revoked_at,
            )
            if self._audit is not None:
                await self._audit.record(
                    AuditEvent.create(
                        id=_audit_id(self._ids),
                        event_type=AuditEventType.SESSION_REVOKED,
                        outcome=AuditOutcome.SUCCESS,
                        occurred_at=revoked_at,
                        actor_user_id=command.user_id,
                        session_id=command.session_id.value,
                        request_context=command.audit_context,
                    )
                )
            await self._transaction.commit()
        except Exception:
            await self._transaction.rollback()
            raise


class LogoutAllSessions:
    """Revoke all sessions for one user."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        transaction: TransactionManager,
        clock: Clock,
        ids: IdGenerator | None = None,
        audit: AuditRecorder | None = None,
    ) -> None:
        self._sessions = sessions
        self._transaction = transaction
        self._clock = clock
        self._ids = ids
        self._audit = audit

    async def __call__(self, command: LogoutAllSessionsCommand) -> LogoutAllSessionsResult:
        """Revoke all active sessions for one user."""

        try:
            revoked_at = _normalize_timestamp(self._clock.now())
            revoked = await self._sessions.revoke_all_for_user(
                command.user_id,
                revoked_at=revoked_at,
            )
            if self._audit is not None:
                await self._audit.record(
                    AuditEvent.create(
                        id=_audit_id(self._ids),
                        event_type=AuditEventType.SESSION_REVOKED_ALL,
                        outcome=AuditOutcome.SUCCESS,
                        occurred_at=revoked_at,
                        actor_user_id=command.user_id,
                        session_id=command.session_id.value if command.session_id else None,
                        request_context=command.audit_context,
                        metadata={"revoked_sessions": revoked},
                    )
                )
            await self._transaction.commit()
            return LogoutAllSessionsResult(revoked_sessions=revoked)
        except Exception:
            await self._transaction.rollback()
            raise


class VerifyAccessToken:
    """Verify access token claims and durable session state."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        access_tokens: AccessTokenCodec,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._access_tokens = access_tokens
        self._clock = clock

    async def __call__(self, token: str) -> VerifiedAccessPrincipal:
        """Return a safe principal for a valid token and active session."""

        try:
            claims = self._access_tokens.verify_token(token)
        except ExpiredAccessTokenError:
            raise
        except InvalidAccessTokenError:
            raise
        session = await self._sessions.get_active_by_id(
            claims.session_id,
            at=_normalize_timestamp(self._clock.now()),
        )
        if session is None:
            msg = "Access token is invalid."
            raise InvalidAccessTokenError(msg)
        if session.user_id != claims.user_id:
            msg = "Access token is invalid."
            raise InvalidAccessTokenError(msg)
        return VerifiedAccessPrincipal(
            user_id=claims.user_id,
            session_id=claims.session_id,
            token_id=claims.token_id,
            issued_at=claims.issued_at,
            expires_at=claims.expires_at,
        )


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "Session lifecycle timestamp must be timezone-aware."
        raise ValueError(msg)
    return value.astimezone(UTC)


def _audit_id(ids: IdGenerator | None) -> UUID:
    if ids is None:
        msg = "Audit recording requires an ID generator."
        raise ValueError(msg)
    return ids.new_uuid()

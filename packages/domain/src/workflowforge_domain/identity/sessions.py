"""Authentication session domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from workflowforge_domain.identity.entities import validate_uuid
from workflowforge_domain.identity.errors import (
    InvalidIdentifier,
    InvalidRefreshTokenState,
    InvalidSessionState,
    InvalidTimestamp,
)

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SessionId:
    """Strongly typed authenticated-session identifier."""

    value: UUID

    @classmethod
    def new(cls) -> SessionId:
        """Create a new random session identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        validate_uuid(self.value, field_name="Session identifier")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class RefreshTokenId:
    """Strongly typed refresh-token record identifier."""

    value: UUID

    @classmethod
    def new(cls) -> RefreshTokenId:
        """Create a new random refresh-token identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        validate_uuid(self.value, field_name="Refresh token identifier")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class RefreshTokenFamilyId:
    """Identifier linking refresh-token rotation lineage."""

    value: UUID

    @classmethod
    def new(cls) -> RefreshTokenFamilyId:
        """Create a new random refresh-token family identifier."""

        return cls(uuid4())

    def __post_init__(self) -> None:
        validate_uuid(self.value, field_name="Refresh token family identifier")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class RefreshTokenDigest:
    """Deterministic SHA-256 digest for an opaque refresh token."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _SHA256_HEX_PATTERN.fullmatch(normalized):
            msg = "Refresh token digest must be a 64-character SHA-256 hex digest."
            raise InvalidIdentifier(msg)
        object.__setattr__(self, "value", normalized)

    def __repr__(self) -> str:
        return "RefreshTokenDigest(<redacted>)"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AuthSession:
    """Durable authenticated session independent of tenant context."""

    id: SessionId
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: SessionId,
        user_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> AuthSession:
        """Create a new active authenticated session."""

        timestamp = _normalize_timestamp(now, field_name="now")
        return cls(
            id=id,
            user_id=user_id,
            created_at=timestamp,
            updated_at=timestamp,
            expires_at=expires_at,
            revoked_at=None,
        )

    def __post_init__(self) -> None:
        validate_uuid(self.user_id, field_name="Session user identifier")
        created_at = _normalize_timestamp(self.created_at, field_name="created_at")
        updated_at = _normalize_timestamp(self.updated_at, field_name="updated_at")
        expires_at = _normalize_timestamp(self.expires_at, field_name="expires_at")
        revoked_at = (
            _normalize_timestamp(self.revoked_at, field_name="revoked_at")
            if self.revoked_at is not None
            else None
        )
        if expires_at <= created_at:
            msg = "Session expiry timestamp must be later than creation timestamp."
            raise InvalidTimestamp(msg)
        if updated_at < created_at:
            msg = "Session updated timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        if revoked_at is not None and revoked_at < created_at:
            msg = "Session revocation timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "revoked_at", revoked_at)

    def is_expired(self, at: datetime) -> bool:
        """Return whether the session has expired at a timestamp."""

        return _normalize_timestamp(at, field_name="at") >= self.expires_at

    def is_active(self, at: datetime) -> bool:
        """Return whether the session is usable at a timestamp."""

        return self.revoked_at is None and not self.is_expired(at)

    def revoke(self, *, now: datetime) -> AuthSession:
        """Return a revoked session. Repeated revocation is idempotent."""

        if self.revoked_at is not None:
            return self
        timestamp = _mutation_timestamp(now, created_at=self.created_at)
        return AuthSession(
            id=self.id,
            user_id=self.user_id,
            created_at=self.created_at,
            updated_at=timestamp,
            expires_at=self.expires_at,
            revoked_at=timestamp,
        )


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    """Durable refresh-token rotation record."""

    id: RefreshTokenId
    session_id: SessionId
    token_family_id: RefreshTokenFamilyId
    token_digest: RefreshTokenDigest
    generation: int
    issued_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    replaced_by_token_id: RefreshTokenId | None = None

    @classmethod
    def issue_initial(
        cls,
        *,
        id: RefreshTokenId,
        session_id: SessionId,
        token_family_id: RefreshTokenFamilyId,
        token_digest: RefreshTokenDigest,
        issued_at: datetime,
        expires_at: datetime,
    ) -> RefreshTokenRecord:
        """Create the first refresh token for a session."""

        return cls(
            id=id,
            session_id=session_id,
            token_family_id=token_family_id,
            token_digest=token_digest,
            generation=0,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def __post_init__(self) -> None:
        if isinstance(self.generation, bool) or self.generation < 0:
            msg = "Refresh token generation must be a non-negative integer."
            raise InvalidRefreshTokenState(msg)
        issued_at = _normalize_timestamp(self.issued_at, field_name="issued_at")
        expires_at = _normalize_timestamp(self.expires_at, field_name="expires_at")
        used_at = (
            _normalize_timestamp(self.used_at, field_name="used_at")
            if self.used_at is not None
            else None
        )
        revoked_at = (
            _normalize_timestamp(self.revoked_at, field_name="revoked_at")
            if self.revoked_at is not None
            else None
        )
        if expires_at <= issued_at:
            msg = "Refresh token expiry timestamp must be later than issue timestamp."
            raise InvalidTimestamp(msg)
        if used_at is not None and used_at < issued_at:
            msg = "Refresh token used timestamp must not be earlier than issue timestamp."
            raise InvalidTimestamp(msg)
        if revoked_at is not None and revoked_at < issued_at:
            msg = "Refresh token revocation timestamp must not be earlier than issue timestamp."
            raise InvalidTimestamp(msg)
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "used_at", used_at)
        object.__setattr__(self, "revoked_at", revoked_at)

    def is_expired(self, at: datetime) -> bool:
        """Return whether the refresh token has expired at a timestamp."""

        return _normalize_timestamp(at, field_name="at") >= self.expires_at

    def is_current(self, at: datetime) -> bool:
        """Return whether the refresh token can be consumed for rotation."""

        return (
            self.used_at is None
            and self.revoked_at is None
            and self.replaced_by_token_id is None
            and not self.is_expired(at)
        )

    def consume(
        self,
        *,
        replacement_token_id: RefreshTokenId,
        now: datetime,
    ) -> RefreshTokenRecord:
        """Return this token marked as consumed by a replacement token."""

        if not self.is_current(now):
            msg = "Refresh token is not current and cannot be rotated."
            raise InvalidRefreshTokenState(msg)
        timestamp = _normalize_timestamp(now, field_name="now")
        return RefreshTokenRecord(
            id=self.id,
            session_id=self.session_id,
            token_family_id=self.token_family_id,
            token_digest=self.token_digest,
            generation=self.generation,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            used_at=timestamp,
            revoked_at=self.revoked_at,
            replaced_by_token_id=replacement_token_id,
        )

    def replacement(
        self,
        *,
        id: RefreshTokenId,
        token_digest: RefreshTokenDigest,
        issued_at: datetime,
        expires_at: datetime,
    ) -> RefreshTokenRecord:
        """Create the next refresh token in this token family."""

        if token_digest == self.token_digest:
            msg = "Refresh token rotation must install a new digest."
            raise InvalidRefreshTokenState(msg)
        return RefreshTokenRecord(
            id=id,
            session_id=self.session_id,
            token_family_id=self.token_family_id,
            token_digest=token_digest,
            generation=self.generation + 1,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def revoke(self, *, now: datetime) -> RefreshTokenRecord:
        """Return a revoked refresh token. Repeated revocation is idempotent."""

        if self.revoked_at is not None:
            return self
        timestamp = _normalize_timestamp(now, field_name="now")
        return RefreshTokenRecord(
            id=self.id,
            session_id=self.session_id,
            token_family_id=self.token_family_id,
            token_digest=self.token_digest,
            generation=self.generation,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            used_at=self.used_at,
            revoked_at=timestamp,
            replaced_by_token_id=self.replaced_by_token_id,
        )


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} timestamp must be timezone-aware."
        raise InvalidTimestamp(msg)
    return value.astimezone(UTC)


def _mutation_timestamp(value: datetime, *, created_at: datetime) -> datetime:
    timestamp = _normalize_timestamp(value, field_name="now")
    if timestamp < created_at:
        msg = "Session mutation timestamp must not be earlier than creation timestamp."
        raise InvalidSessionState(msg)
    return timestamp

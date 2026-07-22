"""Authentication token contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from workflowforge_domain.identity import RefreshTokenDigest, SessionId
from workflowforge_domain.identity.entities import validate_uuid
from workflowforge_domain.identity.errors import InvalidTimestamp


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Verified or issuable access-token claims."""

    user_id: UUID
    session_id: SessionId
    token_id: UUID
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        validate_uuid(self.user_id, field_name="Access token user identifier")
        validate_uuid(self.token_id, field_name="Access token identifier")
        issued_at = _normalize_timestamp(self.issued_at, field_name="issued_at")
        expires_at = _normalize_timestamp(self.expires_at, field_name="expires_at")
        if expires_at <= issued_at:
            msg = "Access token expiry timestamp must be later than issue timestamp."
            raise InvalidTimestamp(msg)
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)


@dataclass(frozen=True, slots=True)
class VerifiedAccessPrincipal:
    """Safe authenticated principal resolved from access token and session state."""

    user_id: UUID
    session_id: SessionId
    token_id: UUID
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        claims = AccessTokenClaims(
            user_id=self.user_id,
            session_id=self.session_id,
            token_id=self.token_id,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
        )
        object.__setattr__(self, "issued_at", claims.issued_at)
        object.__setattr__(self, "expires_at", claims.expires_at)


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """One-time plaintext refresh token returned to the caller only."""

    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Safe token result returned by login and refresh use cases."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    token_type: str
    session_id: SessionId
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "access_token_expires_at",
            _normalize_timestamp(
                self.access_token_expires_at,
                field_name="access_token_expires_at",
            ),
        )
        object.__setattr__(
            self,
            "refresh_token_expires_at",
            _normalize_timestamp(
                self.refresh_token_expires_at,
                field_name="refresh_token_expires_at",
            ),
        )


@dataclass(frozen=True, slots=True)
class GeneratedRefreshCredential:
    """Refresh token plus digest for immediate persistence."""

    token: IssuedRefreshToken
    digest: RefreshTokenDigest


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} timestamp must be timezone-aware."
        raise InvalidTimestamp(msg)
    return value.astimezone(UTC)

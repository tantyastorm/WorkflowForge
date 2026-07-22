"""Password hashing adapters."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from jwt import ExpiredSignatureError, InvalidTokenError
from workflowforge_application.identity import (
    AccessTokenClaims,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    IssuedRefreshToken,
    TokenIssuanceError,
)
from workflowforge_domain.identity import RefreshTokenDigest, SessionId

from workflowforge_infrastructure.config import AuthSettings


class Argon2PasswordHasher:
    """Argon2id password hasher implementation."""

    _dummy_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$"
        "WmF3ZGV2ZHVtbXlzYWx0MQ$"
        "yeOQ2hErJ0XAC+JtSMZPEQajnjCt6apO07B7uh74DQA"
    )

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=Type.ID,
        )

    def __repr__(self) -> str:
        return "Argon2PasswordHasher(algorithm='argon2id')"

    def hash_password(self, plain_password: str) -> str:
        """Return an Argon2id password hash."""

        return self._hasher.hash(plain_password)

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """Return whether a plaintext password matches a stored hash."""

        try:
            return self._hasher.verify(password_hash, plain_password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def dummy_password_hash(self) -> str:
        """Return a stable dummy hash for missing-account verification."""

        return self._dummy_hash

    def needs_rehash(self, password_hash: str) -> bool:
        """Return whether a stored hash should be replaced with current parameters."""

        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (InvalidHashError, VerificationError):
            return False


class Sha256RefreshTokenHasher:
    """SHA-256 digest adapter for high-entropy opaque refresh tokens."""

    def __repr__(self) -> str:
        return "Sha256RefreshTokenHasher(algorithm='sha256')"

    def digest_token(self, plain_token: str) -> RefreshTokenDigest:
        """Return a deterministic SHA-256 digest for a refresh token."""

        return RefreshTokenDigest(hashlib.sha256(plain_token.encode("utf-8")).hexdigest())

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        """Return whether a plaintext refresh token matches a stored digest."""

        expected = self.digest_token(plain_token)
        return hmac.compare_digest(expected.value, token_digest.value)


class JwtAccessTokenCodec:
    """HS256 JWT access-token codec."""

    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings
        self._secret = settings.jwt_signing_secret.get_secret_value()

    def __repr__(self) -> str:
        return (
            "JwtAccessTokenCodec("
            f"algorithm={self._settings.jwt_algorithm!r}, "
            f"issuer={self._settings.jwt_issuer!r}, "
            f"audience={self._settings.jwt_audience!r})"
        )

    def issue_token(self, claims: AccessTokenClaims) -> str:
        """Return an encoded HS256 JWT access token."""

        payload = {
            "sub": str(claims.user_id),
            "sid": str(claims.session_id.value),
            "jti": str(claims.token_id),
            "iat": claims.issued_at,
            "exp": claims.expires_at,
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
        }
        try:
            return jwt.encode(
                payload,
                self._secret,
                algorithm=self._settings.jwt_algorithm,
            )
        except Exception as exc:
            msg = "Access token could not be issued."
            raise TokenIssuanceError(msg) from exc

    def verify_token(self, token: str) -> AccessTokenClaims:
        """Verify and decode an HS256 JWT access token."""

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._settings.jwt_algorithm],
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={
                    "require": ["sub", "sid", "jti", "iat", "exp", "iss", "aud"],
                },
            )
            data = payload
            return AccessTokenClaims(
                user_id=UUID(_require_string(data, "sub")),
                session_id=SessionId(UUID(_require_string(data, "sid"))),
                token_id=UUID(_require_string(data, "jti")),
                issued_at=_timestamp_from_claim(data["iat"], field_name="iat"),
                expires_at=_timestamp_from_claim(data["exp"], field_name="exp"),
            )
        except ExpiredSignatureError as exc:
            msg = "Access token has expired."
            raise ExpiredAccessTokenError(msg) from exc
        except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
            msg = "Access token is invalid."
            raise InvalidAccessTokenError(msg) from exc


class SecretsRefreshTokenGenerator:
    """Cryptographically secure opaque refresh-token generator."""

    def __init__(self, *, token_bytes: int = 32) -> None:
        if token_bytes < 32:
            msg = "Refresh token entropy must be at least 256 bits."
            raise ValueError(msg)
        self._token_bytes = token_bytes

    @classmethod
    def from_settings(cls, settings: AuthSettings) -> SecretsRefreshTokenGenerator:
        """Create a generator from authentication settings."""

        return cls(token_bytes=settings.refresh_token_bytes)

    def __repr__(self) -> str:
        return f"SecretsRefreshTokenGenerator(token_bytes={self._token_bytes})"

    def generate(self) -> IssuedRefreshToken:
        """Return a URL-safe opaque refresh token."""

        return IssuedRefreshToken(secrets.token_urlsafe(self._token_bytes))


class SystemClock:
    """UTC application clock adapter."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC timestamp."""

        return datetime.now(UTC)


class Uuid4Generator:
    """UUID4 ID generator adapter."""

    def new_uuid(self) -> UUID:
        """Return a new UUID4 value."""

        return uuid4()


def _require_string(payload: dict[str, Any], claim: str) -> str:
    value = payload[claim]
    if not isinstance(value, str):
        msg = f"{claim} claim must be a string."
        raise ValueError(msg)
    return value


def _timestamp_from_claim(value: object, *, field_name: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"{field_name} claim must be a numeric date."
        raise ValueError(msg)
    return datetime.fromtimestamp(value, tz=UTC)

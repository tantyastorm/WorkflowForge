"""Token infrastructure adapter tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from pydantic import SecretStr
from workflowforge_application.identity import (
    AccessTokenClaims,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
)
from workflowforge_domain.identity import SessionId
from workflowforge_infrastructure.config import AuthSettings
from workflowforge_infrastructure.identity import (
    JwtAccessTokenCodec,
    SecretsRefreshTokenGenerator,
    Sha256RefreshTokenHasher,
    SystemClock,
    Uuid4Generator,
)

NOW = datetime.now(UTC).replace(microsecond=0)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("77777777-7777-4777-8777-777777777777")
SECRET = "unit-test-jwt-secret-with-at-least-64-characters-for-hs512-checks-0001"


def test_jwt_access_token_codec_issues_and_verifies_minimal_claims() -> None:
    codec = _codec()
    claims = _claims()

    token = codec.issue_token(claims)
    verified = codec.verify_token(token)

    assert verified == claims
    decoded = jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],
        issuer="workflowforge",
        audience="workflowforge-api",
    )
    assert set(decoded) == {"sub", "sid", "jti", "iat", "exp", "iss", "aud"}
    assert "organization_id" not in decoded
    assert SECRET not in repr(codec)
    assert token not in repr(verified)


def test_jwt_access_token_codec_rejects_expired_tokens() -> None:
    codec = _codec()
    expired = _claims(
        issued_at=NOW - timedelta(minutes=30),
        expires_at=NOW - timedelta(minutes=15),
    )

    token = codec.issue_token(expired)

    with pytest.raises(ExpiredAccessTokenError) as exc_info:
        codec.verify_token(token)
    assert token not in str(exc_info.value)


def test_jwt_access_token_codec_rejects_invalid_signature_issuer_audience_and_algorithm() -> None:
    claims = _claims()
    token = _codec().issue_token(claims)

    with pytest.raises(InvalidAccessTokenError):
        JwtAccessTokenCodec(
            AuthSettings(jwt_signing_secret=SecretStr("different-secret-with-enough-length"))
        ).verify_token(token)

    wrong_issuer = JwtAccessTokenCodec(
        AuthSettings(jwt_signing_secret=SecretStr(SECRET), jwt_issuer="other-issuer")
    )
    with pytest.raises(InvalidAccessTokenError):
        wrong_issuer.verify_token(token)

    wrong_audience = JwtAccessTokenCodec(
        AuthSettings(jwt_signing_secret=SecretStr(SECRET), jwt_audience="other-audience")
    )
    with pytest.raises(InvalidAccessTokenError):
        wrong_audience.verify_token(token)

    hs512 = jwt.encode(
        {
            "sub": str(USER_ID),
            "sid": str(SESSION_ID),
            "jti": str(TOKEN_ID),
            "iat": NOW,
            "exp": NOW + timedelta(minutes=15),
            "iss": "workflowforge",
            "aud": "workflowforge-api",
        },
        SECRET,
        algorithm="HS512",
    )
    with pytest.raises(InvalidAccessTokenError):
        _codec().verify_token(hs512)

    unsigned = jwt.encode(
        {
            "sub": str(USER_ID),
            "sid": str(SESSION_ID),
            "jti": str(TOKEN_ID),
            "iat": NOW,
            "exp": NOW + timedelta(minutes=15),
            "iss": "workflowforge",
            "aud": "workflowforge-api",
        },
        "",
        algorithm="none",
    )
    with pytest.raises(InvalidAccessTokenError):
        _codec().verify_token(unsigned)


@pytest.mark.parametrize(
    "payload",
    [
        {"sid": str(SESSION_ID), "jti": str(TOKEN_ID)},
        {"sub": "not-a-uuid", "sid": str(SESSION_ID), "jti": str(TOKEN_ID)},
        {"sub": str(USER_ID), "sid": "not-a-uuid", "jti": str(TOKEN_ID)},
        {"sub": str(USER_ID), "sid": str(SESSION_ID), "jti": "not-a-uuid"},
    ],
)
def test_jwt_access_token_codec_rejects_malformed_or_missing_claims(
    payload: dict[str, str],
) -> None:
    complete_payload: dict[str, object] = {
        **payload,
        "iat": NOW,
        "exp": NOW + timedelta(minutes=15),
        "iss": "workflowforge",
        "aud": "workflowforge-api",
    }
    token = jwt.encode(complete_payload, SECRET, algorithm="HS256")

    with pytest.raises(InvalidAccessTokenError):
        _codec().verify_token(token)


def test_refresh_token_generator_produces_url_safe_high_entropy_tokens() -> None:
    generator = SecretsRefreshTokenGenerator(token_bytes=32)

    first = generator.generate()
    second = generator.generate()

    assert first.value != second.value
    assert len(first.value) >= 43
    assert all(character.isalnum() or character in "-_" for character in first.value)
    assert first.value not in repr(first)


def test_refresh_token_generator_rejects_insufficient_entropy() -> None:
    with pytest.raises(ValueError, match="256 bits"):
        SecretsRefreshTokenGenerator(token_bytes=31)


def test_system_clock_and_uuid_generator_return_valid_values() -> None:
    now = SystemClock().now()
    generated = Uuid4Generator().new_uuid()

    assert now.tzinfo is UTC
    assert generated.int != 0


def test_refresh_token_digest_is_deterministic_through_hasher() -> None:
    hasher = Sha256RefreshTokenHasher()
    token = SecretsRefreshTokenGenerator(token_bytes=32).generate()

    assert hasher.digest_token(token.value) == hasher.digest_token(token.value)


def _codec() -> JwtAccessTokenCodec:
    return JwtAccessTokenCodec(AuthSettings(jwt_signing_secret=SecretStr(SECRET)))


def _claims(
    *,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(minutes=15),
) -> AccessTokenClaims:
    return AccessTokenClaims(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=TOKEN_ID,
        issued_at=issued_at,
        expires_at=expires_at,
    )

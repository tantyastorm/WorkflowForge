"""Authentication session domain tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_domain.identity import (
    AuthSession,
    InvalidIdentifier,
    InvalidRefreshTokenState,
    InvalidSessionState,
    InvalidTimestamp,
    RefreshTokenDigest,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    SessionId,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = SessionId(UUID("44444444-4444-4444-8444-444444444444"))
TOKEN_ID = RefreshTokenId(UUID("55555555-5555-4555-8555-555555555555"))
NEXT_TOKEN_ID = RefreshTokenId(UUID("55555555-5555-4555-8555-666666666666"))
FAMILY_ID = RefreshTokenFamilyId(UUID("66666666-6666-4666-8666-666666666666"))
DIGEST = RefreshTokenDigest("a" * 64)
NEXT_DIGEST = RefreshTokenDigest("b" * 64)


def test_session_creation_and_active_expired_behavior() -> None:
    session = _session()

    assert session.id == SESSION_ID
    assert session.user_id == USER_ID
    assert session.is_active(NOW + timedelta(minutes=1)) is True
    assert session.is_expired(NOW + timedelta(hours=1)) is True
    assert session.is_active(NOW + timedelta(hours=1)) is False


def test_session_rejects_invalid_timestamps_and_identifiers() -> None:
    with pytest.raises(InvalidIdentifier, match="nil UUID"):
        SessionId(UUID(int=0))

    with pytest.raises(InvalidTimestamp, match="later"):
        _session(expires_at=NOW)

    with pytest.raises(InvalidTimestamp, match="timezone-aware"):
        _session(created_at=datetime(2026, 1, 2, 3, 4, 5))


def test_session_revocation_is_idempotent_and_blocks_activity() -> None:
    session = _session()
    revoked = session.revoke(now=NOW + timedelta(minutes=5))

    assert revoked.revoked_at == NOW + timedelta(minutes=5)
    assert revoked.is_active(NOW + timedelta(minutes=6)) is False
    assert revoked.revoke(now=NOW + timedelta(minutes=6)) == revoked

    with pytest.raises(InvalidSessionState, match="mutation"):
        session.revoke(now=NOW - timedelta(seconds=1))


def test_refresh_token_creation_current_and_rotation_lineage() -> None:
    token = _refresh_token()
    replacement = token.replacement(
        id=NEXT_TOKEN_ID,
        token_digest=NEXT_DIGEST,
        issued_at=NOW + timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=2),
    )
    consumed = token.consume(
        replacement_token_id=replacement.id,
        now=NOW + timedelta(minutes=5),
    )

    assert token.is_current(NOW + timedelta(minutes=1)) is True
    assert replacement.generation == 1
    assert replacement.token_family_id == token.token_family_id
    assert consumed.used_at == NOW + timedelta(minutes=5)
    assert consumed.replaced_by_token_id == replacement.id
    assert consumed.is_current(NOW + timedelta(minutes=6)) is False


def test_refresh_token_rejects_invalid_generation_and_digest_reuse() -> None:
    with pytest.raises(InvalidRefreshTokenState, match="generation"):
        _refresh_token(generation=-1)

    with pytest.raises(InvalidIdentifier, match="SHA-256"):
        RefreshTokenDigest("not-a-digest")

    with pytest.raises(InvalidRefreshTokenState, match="new digest"):
        _refresh_token().replacement(
            id=NEXT_TOKEN_ID,
            token_digest=DIGEST,
            issued_at=NOW + timedelta(minutes=5),
            expires_at=NOW + timedelta(hours=2),
        )


def test_refresh_token_rejects_rotation_after_use_revocation_or_expiry() -> None:
    used = _refresh_token().consume(replacement_token_id=NEXT_TOKEN_ID, now=NOW)
    revoked = _refresh_token().revoke(now=NOW)
    expired_at = NOW + timedelta(hours=1)

    for token, at in (
        (used, NOW + timedelta(minutes=1)),
        (revoked, NOW + timedelta(minutes=1)),
        (_refresh_token(), expired_at),
    ):
        with pytest.raises(InvalidRefreshTokenState):
            token.consume(replacement_token_id=NEXT_TOKEN_ID, now=at)


def test_refresh_token_repr_does_not_expose_digest() -> None:
    token = _refresh_token()

    assert DIGEST.value not in repr(token)
    assert DIGEST.value not in repr(DIGEST)


def _session(
    *,
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=1),
) -> AuthSession:
    return AuthSession(
        id=SESSION_ID,
        user_id=USER_ID,
        created_at=created_at,
        updated_at=created_at,
        expires_at=expires_at,
    )


def _refresh_token(*, generation: int = 0) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=TOKEN_ID,
        session_id=SESSION_ID,
        token_family_id=FAMILY_ID,
        token_digest=DIGEST,
        generation=generation,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

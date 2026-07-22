"""User entity tests."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from workflowforge_domain.identity import (
    EmailAddress,
    InvalidDisplayName,
    InvalidTimestamp,
    User,
)
from workflowforge_domain.identity.entities import DISPLAY_NAME_MAX_LENGTH

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC)


def test_user_creation_normalizes_values_and_defaults_active() -> None:
    user = _user(display_name="  Ada   Lovelace  ")

    assert user.id == USER_ID
    assert user.email == EmailAddress("ada@example.com")
    assert user.display_name == "Ada Lovelace"
    assert user.is_active is True
    assert user.created_at == NOW
    assert user.updated_at == NOW
    assert user.disabled_at is None


@pytest.mark.parametrize("display_name", ["", "   ", "\t\n"])
def test_invalid_display_names_are_rejected(display_name: str) -> None:
    with pytest.raises(InvalidDisplayName):
        _user(display_name=display_name)


def test_display_name_length_boundaries_are_enforced() -> None:
    assert _user(display_name="a" * DISPLAY_NAME_MAX_LENGTH).display_name == (
        "a" * DISPLAY_NAME_MAX_LENGTH
    )

    with pytest.raises(InvalidDisplayName, match="at most"):
        _user(display_name="a" * (DISPLAY_NAME_MAX_LENGTH + 1))


def test_user_can_be_disabled_idempotently() -> None:
    user = _user()

    disabled = user.disable(now=LATER)
    repeated = disabled.disable(now=LATER + timedelta(seconds=1))

    assert disabled.is_active is False
    assert disabled.disabled_at == LATER
    assert disabled.updated_at == LATER
    assert repeated is disabled


def test_user_can_be_reactivated_idempotently() -> None:
    disabled = _user().disable(now=LATER)
    reactivated_at = LATER + timedelta(seconds=1)

    reactivated = disabled.reactivate(now=reactivated_at)
    repeated = reactivated.reactivate(now=reactivated_at + timedelta(seconds=1))

    assert reactivated.is_active is True
    assert reactivated.disabled_at is None
    assert reactivated.updated_at == reactivated_at
    assert repeated is reactivated


def test_user_rename_changes_timestamp_only_on_actual_mutation() -> None:
    user = _user()

    renamed = user.rename("  Grace   Hopper  ", now=LATER)
    same = renamed.rename("Grace Hopper", now=LATER + timedelta(seconds=1))

    assert renamed.display_name == "Grace Hopper"
    assert renamed.updated_at == LATER
    assert same is renamed


def test_user_email_change_uses_email_identity_without_verification_claims() -> None:
    user = _user(email=EmailAddress("Ada@Example.com"))

    same = user.change_email(EmailAddress("ada@example.COM"), now=LATER)
    changed = user.change_email(EmailAddress("grace@example.com"), now=LATER)

    assert same is user
    assert changed.email == EmailAddress("grace@example.com")
    assert changed.updated_at == LATER


def test_user_rejects_naive_and_contradictory_timestamps() -> None:
    with pytest.raises(InvalidTimestamp, match="timezone-aware"):
        _user(now=datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(InvalidTimestamp, match="disabled"):
        User(
            id=USER_ID,
            email=EmailAddress("ada@example.com"),
            display_name="Ada",
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
            disabled_at=LATER,
        )

    with pytest.raises(InvalidTimestamp, match="Inactive"):
        User(
            id=USER_ID,
            email=EmailAddress("ada@example.com"),
            display_name="Ada",
            is_active=False,
            created_at=NOW,
            updated_at=NOW,
            disabled_at=None,
        )


def test_user_timestamps_are_normalized_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    user = _user(now=datetime(2026, 1, 2, 5, 4, 5, tzinfo=plus_two))

    assert user.created_at == NOW
    assert user.updated_at == NOW


def _user(
    *,
    email: EmailAddress | None = None,
    display_name: str = "Ada Lovelace",
    now: datetime = NOW,
) -> User:
    return User.create(
        id=USER_ID,
        email=email or EmailAddress("ada@example.com"),
        display_name=display_name,
        now=now,
    )

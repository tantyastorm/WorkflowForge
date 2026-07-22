"""Membership entity tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_domain.identity import (
    InvalidIdentifier,
    InvalidMembershipTransition,
    InvalidTimestamp,
    Membership,
    MembershipAlreadyRemoved,
    MembershipStatus,
    Role,
)

MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC)


def test_invited_membership_creation() -> None:
    membership = _invited()

    assert membership.id == MEMBERSHIP_ID
    assert membership.user_id == USER_ID
    assert membership.organization_id == ORGANIZATION_ID
    assert membership.role is Role.ADMIN
    assert membership.status is MembershipStatus.INVITED
    assert membership.invited_at == NOW
    assert membership.joined_at is None
    assert membership.created_at == NOW
    assert membership.updated_at == NOW


def test_directly_active_membership_creation() -> None:
    membership = _active(role=Role.OWNER)

    assert membership.role is Role.OWNER
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.invited_at is None
    assert membership.joined_at == NOW


def test_invited_membership_can_activate_and_retains_invitation_timestamp() -> None:
    membership = _invited()

    activated = membership.activate(now=LATER)

    assert activated.status is MembershipStatus.ACTIVE
    assert activated.invited_at == NOW
    assert activated.joined_at == LATER
    assert activated.updated_at == LATER


def test_invalid_activation_is_rejected() -> None:
    suspended = _active().suspend(now=LATER)

    with pytest.raises(InvalidMembershipTransition, match="activate"):
        suspended.activate(now=LATER + timedelta(seconds=1))


def test_active_membership_can_suspend() -> None:
    membership = _active()

    suspended = membership.suspend(now=LATER)

    assert suspended.status is MembershipStatus.SUSPENDED
    assert suspended.joined_at == NOW
    assert suspended.suspended_at == LATER
    assert suspended.updated_at == LATER


def test_invalid_suspension_is_rejected() -> None:
    with pytest.raises(InvalidMembershipTransition, match="suspend"):
        _invited().suspend(now=LATER)


def test_suspended_membership_can_reactivate_without_rewriting_joined_at() -> None:
    suspended = _active().suspend(now=LATER)
    reactivated_at = LATER + timedelta(seconds=1)

    reactivated = suspended.reactivate(now=reactivated_at)

    assert reactivated.status is MembershipStatus.ACTIVE
    assert reactivated.joined_at == NOW
    assert reactivated.suspended_at is None
    assert reactivated.updated_at == reactivated_at


def test_invalid_reactivation_is_rejected() -> None:
    with pytest.raises(InvalidMembershipTransition, match="reactivate"):
        _invited().reactivate(now=LATER)


def test_membership_removal_is_deliberately_idempotent() -> None:
    membership = _active()

    removed = membership.remove(now=LATER)
    repeated = removed.remove(now=LATER + timedelta(seconds=1))

    assert removed.status is MembershipStatus.REMOVED
    assert removed.removed_at == LATER
    assert removed.updated_at == LATER
    assert repeated is removed


def test_membership_role_changes_and_same_role_is_idempotent() -> None:
    membership = _active(role=Role.OPERATOR)

    changed = membership.change_role(Role.REVIEWER, now=LATER)
    same = changed.change_role(Role.REVIEWER, now=LATER + timedelta(seconds=1))

    assert changed.role is Role.REVIEWER
    assert changed.updated_at == LATER
    assert same is changed


def test_removed_membership_restrictions_are_explicit() -> None:
    removed = _active().remove(now=LATER)

    with pytest.raises(MembershipAlreadyRemoved):
        removed.activate(now=LATER + timedelta(seconds=1))

    with pytest.raises(MembershipAlreadyRemoved):
        removed.suspend(now=LATER + timedelta(seconds=1))

    with pytest.raises(MembershipAlreadyRemoved):
        removed.reactivate(now=LATER + timedelta(seconds=1))

    with pytest.raises(MembershipAlreadyRemoved):
        removed.change_role(Role.AUDITOR, now=LATER + timedelta(seconds=1))


def test_suspended_membership_role_change_is_rejected() -> None:
    suspended = _active().suspend(now=LATER)

    with pytest.raises(InvalidMembershipTransition, match="suspended"):
        suspended.change_role(Role.AUDITOR, now=LATER + timedelta(seconds=1))


def test_membership_rejects_naive_and_contradictory_timestamps() -> None:
    with pytest.raises(InvalidTimestamp, match="timezone-aware"):
        Membership.invite(
            id=MEMBERSHIP_ID,
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            role=Role.ADMIN,
            now=datetime(2026, 1, 2, 3, 4, 5),
        )

    with pytest.raises(InvalidTimestamp, match="Invited"):
        Membership(
            id=MEMBERSHIP_ID,
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            role=Role.ADMIN,
            status=MembershipStatus.INVITED,
            created_at=NOW,
            updated_at=NOW,
            invited_at=None,
        )

    with pytest.raises(InvalidTimestamp, match="Active"):
        Membership(
            id=MEMBERSHIP_ID,
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            role=Role.ADMIN,
            status=MembershipStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
            joined_at=None,
        )

    with pytest.raises(InvalidTimestamp, match="Removed"):
        Membership(
            id=MEMBERSHIP_ID,
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            role=Role.ADMIN,
            status=MembershipStatus.REMOVED,
            created_at=NOW,
            updated_at=NOW,
            removed_at=None,
        )


def test_membership_uuid_identity_is_preserved_across_transitions() -> None:
    membership = _invited()

    transitioned = membership.activate(now=LATER).change_role(
        Role.OPERATOR,
        now=LATER + timedelta(seconds=1),
    )

    assert transitioned.id == membership.id
    assert transitioned.user_id == membership.user_id
    assert transitioned.organization_id == membership.organization_id
    assert transitioned.created_at == membership.created_at


def test_membership_rejects_nil_identifiers() -> None:
    with pytest.raises(InvalidIdentifier, match="nil UUID"):
        Membership.invite(
            id=UUID(int=0),
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            role=Role.ADMIN,
            now=NOW,
        )


def _invited(*, role: Role = Role.ADMIN) -> Membership:
    return Membership.invite(
        id=MEMBERSHIP_ID,
        user_id=USER_ID,
        organization_id=ORGANIZATION_ID,
        role=role,
        now=NOW,
    )


def _active(*, role: Role = Role.ADMIN) -> Membership:
    return Membership.activate_directly(
        id=MEMBERSHIP_ID,
        user_id=USER_ID,
        organization_id=ORGANIZATION_ID,
        role=role,
        now=NOW,
    )

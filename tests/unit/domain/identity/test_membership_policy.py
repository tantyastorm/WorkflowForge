"""Membership policy tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_domain.identity import (
    LastActiveOwnerViolation,
    Membership,
    MembershipMutation,
    MembershipPolicy,
    Role,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_ORG_ID = UUID("99999999-9999-4999-8999-999999999999")


@pytest.mark.parametrize(
    "mutation",
    [
        MembershipMutation.DEMOTE_OWNER,
        MembershipMutation.SUSPEND_OWNER,
        MembershipMutation.REMOVE_OWNER,
    ],
)
def test_one_active_owner_cannot_be_mutated(mutation: MembershipMutation) -> None:
    owner = _membership(1, role=Role.OWNER)

    with pytest.raises(LastActiveOwnerViolation):
        MembershipPolicy.ensure_not_last_active_owner(
            target=owner,
            memberships=[owner],
            mutation=mutation,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        MembershipMutation.DEMOTE_OWNER,
        MembershipMutation.SUSPEND_OWNER,
        MembershipMutation.REMOVE_OWNER,
    ],
)
def test_one_of_two_active_owners_may_be_mutated(mutation: MembershipMutation) -> None:
    owner = _membership(1, role=Role.OWNER)
    other_owner = _membership(2, role=Role.OWNER)

    MembershipPolicy.ensure_not_last_active_owner(
        target=owner,
        memberships=[owner, other_owner],
        mutation=mutation,
    )


def test_invited_suspended_removed_and_other_org_owners_do_not_count() -> None:
    owner = _membership(1, role=Role.OWNER)
    invited_owner = Membership.invite(
        id=UUID("33333333-3333-4333-8333-000000000002"),
        user_id=UUID("11111111-1111-4111-8111-000000000002"),
        organization_id=ORG_ID,
        role=Role.OWNER,
        now=NOW,
    )
    suspended_owner = _membership(3, role=Role.OWNER).suspend(now=NOW)
    removed_owner = _membership(4, role=Role.OWNER).remove(now=NOW)
    other_org_owner = _membership(5, role=Role.OWNER, organization_id=OTHER_ORG_ID)

    with pytest.raises(LastActiveOwnerViolation):
        MembershipPolicy.ensure_not_last_active_owner(
            target=owner,
            memberships=[
                owner,
                invited_owner,
                suspended_owner,
                removed_owner,
                other_org_owner,
            ],
            mutation=MembershipMutation.REMOVE_OWNER,
        )


def test_non_owner_mutation_remains_allowed() -> None:
    admin = _membership(1, role=Role.ADMIN)

    MembershipPolicy.ensure_not_last_active_owner(
        target=admin,
        memberships=[admin],
        mutation=MembershipMutation.REMOVE_OWNER,
    )


def test_inactive_target_owner_mutation_remains_allowed() -> None:
    suspended_owner = _membership(1, role=Role.OWNER).suspend(now=NOW)

    MembershipPolicy.ensure_not_last_active_owner(
        target=suspended_owner,
        memberships=[suspended_owner],
        mutation=MembershipMutation.REMOVE_OWNER,
    )


def test_duplicate_memberships_do_not_inflate_active_owner_count() -> None:
    owner = _membership(1, role=Role.OWNER)

    with pytest.raises(LastActiveOwnerViolation):
        MembershipPolicy.ensure_not_last_active_owner(
            target=owner,
            memberships=[owner, owner],
            mutation=MembershipMutation.DEMOTE_OWNER,
        )


def test_target_owner_is_counted_even_if_omitted_from_supplied_memberships() -> None:
    owner = _membership(1, role=Role.OWNER)

    with pytest.raises(LastActiveOwnerViolation):
        MembershipPolicy.ensure_not_last_active_owner(
            target=owner,
            memberships=[],
            mutation=MembershipMutation.SUSPEND_OWNER,
        )


def _membership(
    index: int,
    *,
    role: Role,
    organization_id: UUID = ORG_ID,
) -> Membership:
    return Membership.activate_directly(
        id=UUID(f"33333333-3333-4333-8333-{index:012d}"),
        user_id=UUID(f"11111111-1111-4111-8111-{index:012d}"),
        organization_id=organization_id,
        role=role,
        now=NOW,
    )

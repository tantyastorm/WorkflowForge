"""Current-user organization selection tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from workflowforge_application.identity import (
    ListUserOrganizations,
    MembershipRepository,
    OrganizationRepository,
)
from workflowforge_domain.identity import (
    Membership,
    MembershipStatus,
    Organization,
    OrganizationSlug,
    Role,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_A_ID = UUID("22222222-2222-4222-8222-222222222222")
ORG_B_ID = UUID("22222222-2222-4222-8222-333333333333")
ORG_INACTIVE_ID = UUID("22222222-2222-4222-8222-444444444444")
ORG_REMOVED_ID = UUID("22222222-2222-4222-8222-555555555555")


@pytest.mark.asyncio
async def test_list_user_organizations_returns_only_active_memberships_in_stable_order() -> None:
    active_b = _membership(2, organization_id=ORG_B_ID, role=Role.AUDITOR)
    active_a = _membership(1, organization_id=ORG_A_ID, role=Role.OWNER)
    inactive_org_membership = _membership(3, organization_id=ORG_INACTIVE_ID, role=Role.ADMIN)
    removed_membership = _membership(
        4,
        organization_id=ORG_REMOVED_ID,
        role=Role.OPERATOR,
        status=MembershipStatus.REMOVED,
    )
    organization_repository = _OrganizationRepository(
        {
            ORG_A_ID: _organization(ORG_A_ID, name="Beta Works", slug="beta"),
            ORG_B_ID: _organization(ORG_B_ID, name="Alpha Works", slug="alpha"),
            ORG_INACTIVE_ID: _organization(
                ORG_INACTIVE_ID,
                name="Closed Works",
                slug="closed",
            ).deactivate(now=NOW),
            ORG_REMOVED_ID: _organization(
                ORG_REMOVED_ID,
                name="Removed Works",
                slug="removed",
            ),
        }
    )
    query = ListUserOrganizations(
        organizations=cast(OrganizationRepository, organization_repository),
        memberships=_memberships([removed_membership, inactive_org_membership, active_b, active_a]),
    )

    summaries = await query(USER_ID)

    assert [summary.id for summary in summaries] == [ORG_B_ID, ORG_A_ID]
    assert summaries[0].membership_id == active_b.id
    assert summaries[0].membership_role is Role.AUDITOR
    assert summaries[0].membership_status is MembershipStatus.ACTIVE
    assert summaries[1].slug == OrganizationSlug("beta")
    assert organization_repository.list_calls == [USER_ID]
    assert organization_repository.get_calls == []


@pytest.mark.asyncio
async def test_list_user_organizations_enforces_result_bound() -> None:
    query = ListUserOrganizations(
        organizations=_organizations(
            {
                ORG_A_ID: _organization(ORG_A_ID, name="Alpha", slug="alpha"),
                ORG_B_ID: _organization(ORG_B_ID, name="Beta", slug="beta"),
            }
        ),
        memberships=_memberships(
            [
                _membership(1, organization_id=ORG_A_ID, role=Role.OWNER),
                _membership(2, organization_id=ORG_B_ID, role=Role.ADMIN),
            ]
        ),
        max_results=1,
    )

    summaries = await query(USER_ID)

    assert [summary.id for summary in summaries] == [ORG_A_ID]


def _organization(organization_id: UUID, *, name: str, slug: str) -> Organization:
    return Organization.create(
        id=organization_id,
        name=name,
        slug=OrganizationSlug(slug),
        now=NOW,
    )


def _membership(
    index: int,
    *,
    organization_id: UUID,
    role: Role,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    membership = Membership.activate_directly(
        id=UUID(f"33333333-3333-4333-8333-{index:012d}"),
        user_id=USER_ID,
        organization_id=organization_id,
        role=role,
        now=NOW,
    )
    if status is MembershipStatus.ACTIVE:
        return membership
    return membership.remove(now=NOW)


def _organizations(organizations: dict[UUID, Organization]) -> OrganizationRepository:
    return cast(OrganizationRepository, _OrganizationRepository(organizations))


def _memberships(memberships: list[Membership]) -> MembershipRepository:
    return cast(MembershipRepository, _MembershipRepository(memberships))


class _OrganizationRepository:
    def __init__(self, organizations: dict[UUID, Organization]) -> None:
        self._organizations = organizations
        self.list_calls: list[UUID] = []
        self.get_calls: list[UUID] = []

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        self.get_calls.append(organization_id)
        return self._organizations.get(organization_id)

    async def list_for_user(self, user_id: UUID) -> list[Organization]:
        self.list_calls.append(user_id)
        return list(self._organizations.values())

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Unexpected organization repository call: {name}")


class _MembershipRepository:
    def __init__(self, memberships: list[Membership]) -> None:
        self._memberships = memberships

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        return [membership for membership in self._memberships if membership.user_id == user_id]

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Unexpected membership repository call: {name}")

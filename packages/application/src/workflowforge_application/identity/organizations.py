"""Current-user organization selection queries."""

from dataclasses import dataclass
from uuid import UUID

from workflowforge_domain.identity import MembershipStatus, OrganizationSlug, Role

from workflowforge_application.identity.ports import (
    MembershipRepository,
    OrganizationRepository,
)


@dataclass(frozen=True, slots=True)
class UserOrganizationSummary:
    """Safe organization membership summary for authenticated selection."""

    id: UUID
    name: str
    slug: OrganizationSlug
    membership_id: UUID
    membership_role: Role
    membership_status: MembershipStatus


class ListUserOrganizations:
    """List active organizations available to the current authenticated user."""

    DEFAULT_MAX_RESULTS = 1_000

    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        if max_results < 1:
            msg = "Organization list max_results must be positive."
            raise ValueError(msg)
        self._organizations = organizations
        self._memberships = memberships
        self._max_results = max_results

    async def __call__(self, user_id: UUID) -> tuple[UserOrganizationSummary, ...]:
        memberships = await self._memberships.list_for_user(user_id)
        organizations = {
            organization.id: organization
            for organization in await self._organizations.list_for_user(user_id)
            if organization.is_active
        }
        summaries: list[UserOrganizationSummary] = []

        for membership in memberships:
            if membership.status is not MembershipStatus.ACTIVE:
                continue
            organization = organizations.get(membership.organization_id)
            if organization is None:
                continue
            summaries.append(
                UserOrganizationSummary(
                    id=organization.id,
                    name=organization.name,
                    slug=organization.slug,
                    membership_id=membership.id,
                    membership_role=membership.role,
                    membership_status=membership.status,
                )
            )

        return tuple(
            sorted(
                summaries,
                key=lambda item: (item.name.casefold(), item.slug.value, str(item.id)),
            )
        )[: self._max_results]

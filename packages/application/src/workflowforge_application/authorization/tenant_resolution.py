"""Tenant context resolution from durable identity state."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from workflowforge_domain.identity import MembershipStatus

from workflowforge_application.authorization.context import TenantContext
from workflowforge_application.authorization.errors import (
    TenantAccessDenied,
    TenantMembershipInactive,
)
from workflowforge_application.identity import MembershipRepository, OrganizationRepository


@dataclass(frozen=True, slots=True)
class ResolveTenantContextCommand:
    """Input for resolving a selected organization into a tenant context."""

    user_id: UUID
    organization_id: UUID


class ResolveTenantContext:
    """Resolve tenant authorization context from current durable membership state."""

    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships

    async def __call__(self, command: ResolveTenantContextCommand) -> TenantContext:
        """Return a tenant context or raise a transport-neutral denial."""

        organization = await self._organizations.get_by_id(command.organization_id)
        if organization is None:
            raise TenantAccessDenied(
                user_id=command.user_id,
                organization_id=command.organization_id,
                reason="organization not found",
            )
        if not organization.is_active:
            raise TenantAccessDenied(
                user_id=command.user_id,
                organization_id=command.organization_id,
                reason="organization inactive",
            )

        membership = await self._memberships.get_by_user_and_organization(
            user_id=command.user_id,
            organization_id=command.organization_id,
        )
        if membership is None:
            raise TenantAccessDenied(
                user_id=command.user_id,
                organization_id=command.organization_id,
                reason="membership not found",
            )
        if membership.status is not MembershipStatus.ACTIVE:
            raise TenantMembershipInactive(
                user_id=command.user_id,
                organization_id=command.organization_id,
                membership_id=membership.id,
                status=membership.status,
            )

        return TenantContext.create(
            user_id=command.user_id,
            organization_id=command.organization_id,
            membership_id=membership.id,
            role=membership.role,
        )

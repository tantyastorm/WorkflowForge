"""Identity application repository ports."""

from typing import Protocol
from uuid import UUID

from workflowforge_domain.identity import (
    EmailAddress,
    Membership,
    Organization,
    OrganizationSlug,
    User,
)


class UserRepository(Protocol):
    """Persistence port for users."""

    async def add(self, user: User) -> User:
        """Persist a user."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return a user by ID, when present."""

    async def get_by_normalized_email(self, email: EmailAddress | str) -> User | None:
        """Return a user by normalized email, when present."""

    async def update(self, user: User) -> User:
        """Persist an existing user state."""


class OrganizationRepository(Protocol):
    """Persistence port for organizations."""

    async def add(self, organization: Organization) -> Organization:
        """Persist an organization."""

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        """Return an organization by ID, when present."""

    async def get_by_slug(self, slug: OrganizationSlug | str) -> Organization | None:
        """Return an organization by slug, when present."""

    async def list_for_user(self, user_id: UUID) -> list[Organization]:
        """Return organizations where a user has membership."""

    async def update(self, organization: Organization) -> Organization:
        """Persist an existing organization state."""


class MembershipRepository(Protocol):
    """Persistence port for organization memberships."""

    async def add(self, membership: Membership) -> Membership:
        """Persist a membership."""

    async def get_by_id(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        """Return a tenant-scoped membership by ID, when present."""

    async def get_by_user_and_organization(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None:
        """Return a user's membership in an organization, when present."""

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        """Return memberships for an organization."""

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        """Return memberships for a user."""

    async def update(self, membership: Membership) -> Membership:
        """Persist an existing membership state."""

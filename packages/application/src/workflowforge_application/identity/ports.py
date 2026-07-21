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

from workflowforge_application.identity.credentials import PasswordCredential


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


class PasswordHasher(Protocol):
    """Password hashing port for credential use cases."""

    def hash_password(self, plain_password: str) -> str:
        """Return a durable password hash for a plaintext password."""

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """Return whether a plaintext password matches a stored hash."""

    def dummy_password_hash(self) -> str:
        """Return a safe dummy hash for missing-account verification."""


class PasswordCredentialRepository(Protocol):
    """Persistence port for password credentials."""

    async def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        """Return a user's password credential, when present."""

    async def set_for_user(self, credential: PasswordCredential) -> PasswordCredential:
        """Create or replace one user's password credential."""


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

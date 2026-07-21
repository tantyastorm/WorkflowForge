"""Identity application repository ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
    Membership,
    Organization,
    OrganizationSlug,
    RefreshTokenDigest,
    RefreshTokenRecord,
    SessionId,
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


class RefreshTokenHasher(Protocol):
    """Digesting port for high-entropy opaque refresh tokens."""

    def digest_token(self, plain_token: str) -> RefreshTokenDigest:
        """Return a deterministic digest for a refresh token."""

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        """Return whether a plaintext token matches a stored digest."""


class PasswordCredentialRepository(Protocol):
    """Persistence port for password credentials."""

    async def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        """Return a user's password credential, when present."""

    async def set_for_user(self, credential: PasswordCredential) -> PasswordCredential:
        """Create or replace one user's password credential."""


class SessionRepository(Protocol):
    """Persistence port for authenticated sessions and refresh-token lineage."""

    async def add(
        self,
        *,
        session: AuthSession,
        refresh_token: RefreshTokenRecord,
    ) -> AuthSession:
        """Persist a session and its initial refresh token atomically."""

    async def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        """Return a session by ID, when present."""

    async def get_active_by_id(
        self,
        session_id: SessionId,
        *,
        at: datetime,
    ) -> AuthSession | None:
        """Return a non-revoked, non-expired session by ID, when present."""

    async def get_refresh_token_by_digest(
        self,
        token_digest: RefreshTokenDigest,
    ) -> RefreshTokenRecord | None:
        """Return a refresh-token record by digest, when present."""

    async def update(self, session: AuthSession) -> AuthSession:
        """Persist session lifecycle state."""

    async def revoke(self, session_id: SessionId, *, revoked_at: datetime) -> AuthSession:
        """Revoke one session and its current refresh credentials."""

    async def revoke_all_for_user(self, user_id: UUID, *, revoked_at: datetime) -> int:
        """Revoke all active sessions for one user and return the affected count."""

    async def rotate_refresh_token(
        self,
        *,
        session_id: SessionId,
        expected_digest: RefreshTokenDigest,
        expected_generation: int,
        replacement: RefreshTokenRecord,
        rotated_at: datetime,
    ) -> RefreshTokenRecord:
        """Atomically consume the expected refresh token and persist its replacement."""


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

"""Identity and tenancy entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from workflowforge_domain.identity.enums import MembershipStatus, Role
from workflowforge_domain.identity.errors import (
    InvalidDisplayName,
    InvalidIdentifier,
    InvalidMembershipTransition,
    InvalidOrganizationName,
    InvalidTimestamp,
    MembershipAlreadyRemoved,
)
from workflowforge_domain.identity.value_objects import (
    EmailAddress,
    OrganizationSlug,
)

DISPLAY_NAME_MIN_LENGTH = 1
DISPLAY_NAME_MAX_LENGTH = 120
ORGANIZATION_NAME_MIN_LENGTH = 1
ORGANIZATION_NAME_MAX_LENGTH = 160


@dataclass(frozen=True, slots=True)
class User:
    """Framework-independent user identity."""

    id: UUID
    email: EmailAddress
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        email: EmailAddress,
        display_name: str,
        now: datetime,
    ) -> User:
        """Create an active user."""

        timestamp = normalize_timestamp(now, field_name="now")
        return cls(
            id=id,
            email=email,
            display_name=display_name,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
            disabled_at=None,
        )

    def __post_init__(self) -> None:
        validate_uuid(self.id, field_name="User identifier")
        object.__setattr__(
            self,
            "display_name",
            normalize_display_name(self.display_name),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            normalize_timestamp(self.updated_at, field_name="updated_at"),
        )
        if self.disabled_at is not None:
            object.__setattr__(
                self,
                "disabled_at",
                normalize_timestamp(self.disabled_at, field_name="disabled_at"),
            )
        if self.updated_at < self.created_at:
            msg = "User updated timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        if self.is_active and self.disabled_at is not None:
            msg = "Active user must not have a disabled timestamp."
            raise InvalidTimestamp(msg)
        if not self.is_active and self.disabled_at is None:
            msg = "Inactive user must have a disabled timestamp."
            raise InvalidTimestamp(msg)

    def disable(self, *, now: datetime) -> User:
        """Return a disabled user, preserving idempotency."""

        if not self.is_active:
            return self
        timestamp = self._mutation_timestamp(now)
        return User(
            id=self.id,
            email=self.email,
            display_name=self.display_name,
            is_active=False,
            created_at=self.created_at,
            updated_at=timestamp,
            disabled_at=timestamp,
        )

    def reactivate(self, *, now: datetime) -> User:
        """Return an active user, preserving idempotency."""

        if self.is_active:
            return self
        timestamp = self._mutation_timestamp(now)
        return User(
            id=self.id,
            email=self.email,
            display_name=self.display_name,
            is_active=True,
            created_at=self.created_at,
            updated_at=timestamp,
            disabled_at=None,
        )

    def rename(self, display_name: str, *, now: datetime) -> User:
        """Return a user with an updated display name."""

        normalized_display_name = normalize_display_name(display_name)
        if normalized_display_name == self.display_name:
            return self
        timestamp = self._mutation_timestamp(now)
        return User(
            id=self.id,
            email=self.email,
            display_name=normalized_display_name,
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=timestamp,
            disabled_at=self.disabled_at,
        )

    def change_email(self, email: EmailAddress, *, now: datetime) -> User:
        """Return a user with a new email identity without implying verification."""

        if email == self.email:
            return self
        timestamp = self._mutation_timestamp(now)
        return User(
            id=self.id,
            email=email,
            display_name=self.display_name,
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=timestamp,
            disabled_at=self.disabled_at,
        )

    def _mutation_timestamp(self, value: datetime) -> datetime:
        timestamp = normalize_timestamp(value, field_name="now")
        if timestamp < self.created_at:
            msg = "User mutation timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        return timestamp


@dataclass(frozen=True, slots=True)
class Organization:
    """Framework-independent organization tenant."""

    id: UUID
    name: str
    slug: OrganizationSlug
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        name: str,
        slug: OrganizationSlug,
        now: datetime,
    ) -> Organization:
        """Create an active organization."""

        timestamp = normalize_timestamp(now, field_name="now")
        return cls(
            id=id,
            name=name,
            slug=slug,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
            deactivated_at=None,
        )

    def __post_init__(self) -> None:
        validate_uuid(self.id, field_name="Organization identifier")
        object.__setattr__(self, "name", normalize_organization_name(self.name))
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            normalize_timestamp(self.updated_at, field_name="updated_at"),
        )
        if self.deactivated_at is not None:
            object.__setattr__(
                self,
                "deactivated_at",
                normalize_timestamp(self.deactivated_at, field_name="deactivated_at"),
            )
        if self.updated_at < self.created_at:
            msg = "Organization updated timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        if self.is_active and self.deactivated_at is not None:
            msg = "Active organization must not have a deactivated timestamp."
            raise InvalidTimestamp(msg)
        if not self.is_active and self.deactivated_at is None:
            msg = "Inactive organization must have a deactivated timestamp."
            raise InvalidTimestamp(msg)

    def rename(self, name: str, *, now: datetime) -> Organization:
        """Return an organization with an updated name; slug is unchanged."""

        normalized_name = normalize_organization_name(name)
        if normalized_name == self.name:
            return self
        timestamp = self._mutation_timestamp(now)
        return Organization(
            id=self.id,
            name=normalized_name,
            slug=self.slug,
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=timestamp,
            deactivated_at=self.deactivated_at,
        )

    def deactivate(self, *, now: datetime) -> Organization:
        """Return a deactivated organization, preserving idempotency."""

        if not self.is_active:
            return self
        timestamp = self._mutation_timestamp(now)
        return Organization(
            id=self.id,
            name=self.name,
            slug=self.slug,
            is_active=False,
            created_at=self.created_at,
            updated_at=timestamp,
            deactivated_at=timestamp,
        )

    def reactivate(self, *, now: datetime) -> Organization:
        """Return an active organization, preserving idempotency."""

        if self.is_active:
            return self
        timestamp = self._mutation_timestamp(now)
        return Organization(
            id=self.id,
            name=self.name,
            slug=self.slug,
            is_active=True,
            created_at=self.created_at,
            updated_at=timestamp,
            deactivated_at=None,
        )

    def _mutation_timestamp(self, value: datetime) -> datetime:
        timestamp = normalize_timestamp(value, field_name="now")
        if timestamp < self.created_at:
            msg = "Organization mutation timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        return timestamp


@dataclass(frozen=True, slots=True)
class Membership:
    """Membership connecting exactly one user to one organization."""

    id: UUID
    user_id: UUID
    organization_id: UUID
    role: Role
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    suspended_at: datetime | None = None
    removed_at: datetime | None = None

    @classmethod
    def invite(
        cls,
        *,
        id: UUID,
        user_id: UUID,
        organization_id: UUID,
        role: Role,
        now: datetime,
    ) -> Membership:
        """Create an invited membership."""

        timestamp = normalize_timestamp(now, field_name="now")
        return cls(
            id=id,
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            status=MembershipStatus.INVITED,
            created_at=timestamp,
            updated_at=timestamp,
            invited_at=timestamp,
        )

    @classmethod
    def activate_directly(
        cls,
        *,
        id: UUID,
        user_id: UUID,
        organization_id: UUID,
        role: Role,
        now: datetime,
    ) -> Membership:
        """Create an active membership for owner/bootstrap flows."""

        timestamp = normalize_timestamp(now, field_name="now")
        return cls(
            id=id,
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            status=MembershipStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
            joined_at=timestamp,
        )

    def __post_init__(self) -> None:
        validate_uuid(self.id, field_name="Membership identifier")
        validate_uuid(self.user_id, field_name="Membership user identifier")
        validate_uuid(
            self.organization_id,
            field_name="Membership organization identifier",
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_timestamp(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            normalize_timestamp(self.updated_at, field_name="updated_at"),
        )
        for field_name in (
            "invited_at",
            "joined_at",
            "suspended_at",
            "removed_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    normalize_timestamp(value, field_name=field_name),
                )
        if self.updated_at < self.created_at:
            msg = "Membership updated timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        self._validate_lifecycle_state()

    def activate(self, *, now: datetime) -> Membership:
        """Return an active invited membership."""

        if self.status is MembershipStatus.ACTIVE:
            return self
        if self.status is not MembershipStatus.INVITED:
            self._raise_invalid_transition("activate")
        timestamp = self._mutation_timestamp(now)
        return Membership(
            id=self.id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            role=self.role,
            status=MembershipStatus.ACTIVE,
            created_at=self.created_at,
            updated_at=timestamp,
            invited_at=self.invited_at,
            joined_at=timestamp,
        )

    def suspend(self, *, now: datetime) -> Membership:
        """Return a suspended active membership."""

        if self.status is not MembershipStatus.ACTIVE:
            self._raise_invalid_transition("suspend")
        timestamp = self._mutation_timestamp(now)
        return Membership(
            id=self.id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            role=self.role,
            status=MembershipStatus.SUSPENDED,
            created_at=self.created_at,
            updated_at=timestamp,
            invited_at=self.invited_at,
            joined_at=self.joined_at,
            suspended_at=timestamp,
        )

    def reactivate(self, *, now: datetime) -> Membership:
        """Return an active suspended membership without rewriting joined_at."""

        if self.status is MembershipStatus.ACTIVE:
            return self
        if self.status is not MembershipStatus.SUSPENDED:
            self._raise_invalid_transition("reactivate")
        timestamp = self._mutation_timestamp(now)
        return Membership(
            id=self.id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            role=self.role,
            status=MembershipStatus.ACTIVE,
            created_at=self.created_at,
            updated_at=timestamp,
            invited_at=self.invited_at,
            joined_at=self.joined_at,
            suspended_at=None,
        )

    def remove(self, *, now: datetime) -> Membership:
        """Return a removed membership; repeated removal is idempotent."""

        if self.status is MembershipStatus.REMOVED:
            return self
        timestamp = self._mutation_timestamp(now)
        return Membership(
            id=self.id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            role=self.role,
            status=MembershipStatus.REMOVED,
            created_at=self.created_at,
            updated_at=timestamp,
            invited_at=self.invited_at,
            joined_at=self.joined_at,
            suspended_at=self.suspended_at,
            removed_at=timestamp,
        )

    def change_role(self, role: Role, *, now: datetime) -> Membership:
        """Return a membership with a changed role."""

        if self.status is MembershipStatus.REMOVED:
            self._raise_removed("change role")
        if self.status is MembershipStatus.SUSPENDED:
            self._raise_invalid_transition("change role while suspended")
        if role is self.role:
            return self
        timestamp = self._mutation_timestamp(now)
        return Membership(
            id=self.id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            role=role,
            status=self.status,
            created_at=self.created_at,
            updated_at=timestamp,
            invited_at=self.invited_at,
            joined_at=self.joined_at,
            suspended_at=self.suspended_at,
            removed_at=self.removed_at,
        )

    def _validate_lifecycle_state(self) -> None:
        if self.status is MembershipStatus.INVITED:
            if self.invited_at is None:
                msg = "Invited membership must have an invited timestamp."
                raise InvalidTimestamp(msg)
            if self.joined_at is not None or self.suspended_at is not None:
                msg = "Invited membership cannot have joined or suspended timestamps."
                raise InvalidTimestamp(msg)
            if self.removed_at is not None:
                msg = "Invited membership cannot have a removed timestamp."
                raise InvalidTimestamp(msg)
        elif self.status is MembershipStatus.ACTIVE:
            if self.joined_at is None:
                msg = "Active membership must have a joined timestamp."
                raise InvalidTimestamp(msg)
            if self.suspended_at is not None or self.removed_at is not None:
                msg = "Active membership cannot have suspended or removed timestamps."
                raise InvalidTimestamp(msg)
        elif self.status is MembershipStatus.SUSPENDED:
            if self.joined_at is None or self.suspended_at is None:
                msg = "Suspended membership must have joined and suspended timestamps."
                raise InvalidTimestamp(msg)
            if self.removed_at is not None:
                msg = "Suspended membership cannot have a removed timestamp."
                raise InvalidTimestamp(msg)
        elif self.status is MembershipStatus.REMOVED:
            if self.removed_at is None:
                msg = "Removed membership must have a removed timestamp."
                raise InvalidTimestamp(msg)
        else:
            msg = "Membership status is invalid."
            raise InvalidMembershipTransition(msg)

    def _mutation_timestamp(self, value: datetime) -> datetime:
        timestamp = normalize_timestamp(value, field_name="now")
        if timestamp < self.created_at:
            msg = "Membership mutation timestamp must not be earlier than creation timestamp."
            raise InvalidTimestamp(msg)
        return timestamp

    def _raise_invalid_transition(self, operation: str) -> None:
        if self.status is MembershipStatus.REMOVED:
            self._raise_removed(operation)
        msg = f"Cannot {operation} membership in {self.status.value} status."
        raise InvalidMembershipTransition(msg)

    def _raise_removed(self, operation: str) -> None:
        msg = f"Cannot {operation} a removed membership."
        raise MembershipAlreadyRemoved(msg)


def normalize_display_name(value: str) -> str:
    """Normalize and validate a user display name."""

    normalized = " ".join(value.strip().split())
    if len(normalized) < DISPLAY_NAME_MIN_LENGTH:
        msg = "Display name must not be empty."
        raise InvalidDisplayName(msg)
    if len(normalized) > DISPLAY_NAME_MAX_LENGTH:
        msg = f"Display name must be at most {DISPLAY_NAME_MAX_LENGTH} characters."
        raise InvalidDisplayName(msg)
    return normalized


def normalize_organization_name(value: str) -> str:
    """Normalize and validate an organization name."""

    normalized = " ".join(value.strip().split())
    if len(normalized) < ORGANIZATION_NAME_MIN_LENGTH:
        msg = "Organization name must not be empty."
        raise InvalidOrganizationName(msg)
    if len(normalized) > ORGANIZATION_NAME_MAX_LENGTH:
        msg = f"Organization name must be at most {ORGANIZATION_NAME_MAX_LENGTH} characters."
        raise InvalidOrganizationName(msg)
    return normalized


def normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    """Normalize a timezone-aware timestamp to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} timestamp must be timezone-aware."
        raise InvalidTimestamp(msg)
    return value.astimezone(UTC)


def validate_uuid(value: UUID, *, field_name: str) -> None:
    """Validate a non-nil UUID identifier."""

    if value.int == 0:
        msg = f"{field_name} must not be the nil UUID."
        raise InvalidIdentifier(msg)

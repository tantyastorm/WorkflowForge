"""SQLAlchemy identity repositories."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.identity import (
    DuplicateNormalizedEmailError,
    DuplicateOrganizationMembershipError,
    DuplicateOrganizationSlugError,
    MembershipRepository,
    MissingIdentityReferenceError,
    OrganizationRepository,
    UserRepository,
)
from workflowforge_domain.identity import (
    EmailAddress,
    Membership,
    MembershipStatus,
    Organization,
    OrganizationSlug,
    Role,
    User,
)

from workflowforge_infrastructure.identity.models import (
    MembershipRecord,
    OrganizationRecord,
    UserRecord,
)


class SqlAlchemyUserRepository(UserRepository):
    """SQLAlchemy implementation of the user repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        """Persist a user."""

        record = _record_from_user(user)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "User normalized email already exists."
            raise DuplicateNormalizedEmailError(msg) from exc
        return _user_from_record(record)

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return a user by ID, when present."""

        record = await self._session.get(UserRecord, user_id)
        if record is None:
            return None
        return _user_from_record(record)

    async def get_by_normalized_email(self, email: EmailAddress | str) -> User | None:
        """Return a user by normalized email, when present."""

        normalized_email = email.normalized if isinstance(email, EmailAddress) else email
        result = await self._session.execute(
            select(UserRecord).where(UserRecord.normalized_email == normalized_email)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _user_from_record(record)

    async def update(self, user: User) -> User:
        """Persist an existing user state."""

        record = await self._session.get(UserRecord, user.id)
        if record is None:
            msg = "User does not exist."
            raise MissingIdentityReferenceError(msg)
        _update_user_record(record, user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "User normalized email already exists."
            raise DuplicateNormalizedEmailError(msg) from exc
        return _user_from_record(record)


class SqlAlchemyOrganizationRepository(OrganizationRepository):
    """SQLAlchemy implementation of the organization repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> Organization:
        """Persist an organization."""

        record = _record_from_organization(organization)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Organization slug already exists."
            raise DuplicateOrganizationSlugError(msg) from exc
        return _organization_from_record(record)

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        """Return an organization by ID, when present."""

        record = await self._session.get(OrganizationRecord, organization_id)
        if record is None:
            return None
        return _organization_from_record(record)

    async def get_by_slug(self, slug: OrganizationSlug | str) -> Organization | None:
        """Return an organization by slug, when present."""

        slug_value = slug.value if isinstance(slug, OrganizationSlug) else slug
        result = await self._session.execute(
            select(OrganizationRecord).where(OrganizationRecord.slug == slug_value)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _organization_from_record(record)

    async def list_for_user(self, user_id: UUID) -> list[Organization]:
        """Return organizations where a user has membership."""

        result = await self._session.execute(
            select(OrganizationRecord)
            .join(MembershipRecord, MembershipRecord.organization_id == OrganizationRecord.id)
            .where(MembershipRecord.user_id == user_id)
            .order_by(OrganizationRecord.created_at, OrganizationRecord.id)
        )
        return [_organization_from_record(record) for record in result.scalars()]

    async def update(self, organization: Organization) -> Organization:
        """Persist an existing organization state."""

        record = await self._session.get(OrganizationRecord, organization.id)
        if record is None:
            msg = "Organization does not exist."
            raise MissingIdentityReferenceError(msg)
        _update_organization_record(record, organization)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Organization slug already exists."
            raise DuplicateOrganizationSlugError(msg) from exc
        return _organization_from_record(record)


class SqlAlchemyMembershipRepository(MembershipRepository):
    """SQLAlchemy implementation of the membership repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> Membership:
        """Persist a membership."""

        record = _record_from_membership(membership)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            _raise_membership_integrity_error(exc)
        return _membership_from_record(record)

    async def get_by_id(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        """Return a tenant-scoped membership by ID, when present."""

        result = await self._session.execute(
            select(MembershipRecord).where(
                MembershipRecord.organization_id == organization_id,
                MembershipRecord.id == membership_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _membership_from_record(record)

    async def get_by_user_and_organization(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None:
        """Return a user's membership in an organization, when present."""

        result = await self._session.execute(
            select(MembershipRecord).where(
                MembershipRecord.user_id == user_id,
                MembershipRecord.organization_id == organization_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _membership_from_record(record)

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        """Return memberships for an organization."""

        result = await self._session.execute(
            select(MembershipRecord)
            .where(MembershipRecord.organization_id == organization_id)
            .order_by(MembershipRecord.created_at, MembershipRecord.id)
        )
        return [_membership_from_record(record) for record in result.scalars()]

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        """Return memberships for a user."""

        result = await self._session.execute(
            select(MembershipRecord)
            .where(MembershipRecord.user_id == user_id)
            .order_by(MembershipRecord.created_at, MembershipRecord.id)
        )
        return [_membership_from_record(record) for record in result.scalars()]

    async def update(self, membership: Membership) -> Membership:
        """Persist an existing membership state."""

        result = await self._session.execute(
            select(MembershipRecord).where(
                MembershipRecord.organization_id == membership.organization_id,
                MembershipRecord.id == membership.id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            msg = "Membership does not exist."
            raise MissingIdentityReferenceError(msg)
        _update_membership_record(record, membership)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            _raise_membership_integrity_error(exc)
        return _membership_from_record(record)


def _record_from_user(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        email=user.email.display,
        normalized_email=user.email.normalized,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        disabled_at=user.disabled_at,
    )


def _user_from_record(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=EmailAddress(record.email),
        display_name=record.display_name,
        is_active=record.is_active,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        disabled_at=record.disabled_at.astimezone(UTC) if record.disabled_at else None,
    )


def _update_user_record(record: UserRecord, user: User) -> None:
    record.email = user.email.display
    record.normalized_email = user.email.normalized
    record.display_name = user.display_name
    record.is_active = user.is_active
    record.created_at = user.created_at
    record.updated_at = user.updated_at
    record.disabled_at = user.disabled_at


def _record_from_organization(organization: Organization) -> OrganizationRecord:
    return OrganizationRecord(
        id=organization.id,
        name=organization.name,
        slug=organization.slug.value,
        is_active=organization.is_active,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
        deactivated_at=organization.deactivated_at,
    )


def _organization_from_record(record: OrganizationRecord) -> Organization:
    return Organization(
        id=record.id,
        name=record.name,
        slug=OrganizationSlug(record.slug),
        is_active=record.is_active,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        deactivated_at=record.deactivated_at.astimezone(UTC) if record.deactivated_at else None,
    )


def _update_organization_record(
    record: OrganizationRecord,
    organization: Organization,
) -> None:
    record.name = organization.name
    record.slug = organization.slug.value
    record.is_active = organization.is_active
    record.created_at = organization.created_at
    record.updated_at = organization.updated_at
    record.deactivated_at = organization.deactivated_at


def _record_from_membership(membership: Membership) -> MembershipRecord:
    return MembershipRecord(
        id=membership.id,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        role=membership.role.value,
        status=membership.status.value,
        invited_at=membership.invited_at,
        joined_at=membership.joined_at,
        suspended_at=membership.suspended_at,
        removed_at=membership.removed_at,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _membership_from_record(record: MembershipRecord) -> Membership:
    return Membership(
        id=record.id,
        user_id=record.user_id,
        organization_id=record.organization_id,
        role=Role(record.role),
        status=MembershipStatus(record.status),
        invited_at=record.invited_at.astimezone(UTC) if record.invited_at else None,
        joined_at=record.joined_at.astimezone(UTC) if record.joined_at else None,
        suspended_at=record.suspended_at.astimezone(UTC) if record.suspended_at else None,
        removed_at=record.removed_at.astimezone(UTC) if record.removed_at else None,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
    )


def _update_membership_record(record: MembershipRecord, membership: Membership) -> None:
    record.user_id = membership.user_id
    record.organization_id = membership.organization_id
    record.role = membership.role.value
    record.status = membership.status.value
    record.invited_at = membership.invited_at
    record.joined_at = membership.joined_at
    record.suspended_at = membership.suspended_at
    record.removed_at = membership.removed_at
    record.created_at = membership.created_at
    record.updated_at = membership.updated_at


def _raise_membership_integrity_error(exc: IntegrityError) -> None:
    message = str(exc.orig)
    if "uq_memberships_organization_user" in message:
        msg = "Organization membership already exists."
        raise DuplicateOrganizationMembershipError(msg) from exc
    msg = "Membership references a missing user or organization."
    raise MissingIdentityReferenceError(msg) from exc

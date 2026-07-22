"""SQLAlchemy identity repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from workflowforge_application.identity import (
    DuplicateNormalizedEmailError,
    DuplicateOrganizationMembershipError,
    DuplicateOrganizationSlugError,
    DuplicateRefreshTokenDigestError,
    MembershipRepository,
    MissingIdentityReferenceError,
    OrganizationRepository,
    PasswordCredential,
    PasswordCredentialRepository,
    RefreshRotationConflictError,
    SessionNotFoundError,
    SessionRepository,
    UserRepository,
)
from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
    Membership,
    MembershipStatus,
    Organization,
    OrganizationSlug,
    RefreshTokenDigest,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    Role,
    SessionId,
    User,
)

from workflowforge_infrastructure.identity.models import (
    AuthSessionRecord,
    MembershipRecord,
    OrganizationRecord,
    PasswordCredentialRecord,
    RefreshTokenRecordModel,
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


class SqlAlchemyPasswordCredentialRepository(PasswordCredentialRepository):
    """SQLAlchemy implementation of the password credential repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        """Return a user's password credential, when present."""

        record = await self._session.get(PasswordCredentialRecord, user_id)
        if record is None:
            return None
        return _password_credential_from_record(record)

    async def set_for_user(self, credential: PasswordCredential) -> PasswordCredential:
        """Create or replace a user's password credential."""

        record = await self._session.get(PasswordCredentialRecord, credential.user_id)
        if record is None:
            record = _record_from_password_credential(credential)
            self._session.add(record)
        else:
            _update_password_credential_record(record, credential)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = "Password credential references a missing user."
            raise MissingIdentityReferenceError(msg) from exc
        return _password_credential_from_record(record)


class SqlAlchemySessionRepository(SessionRepository):
    """SQLAlchemy implementation of the session repository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        session: AuthSession,
        refresh_token: RefreshTokenRecord,
    ) -> AuthSession:
        """Persist a session and initial refresh token atomically."""

        session_record = _record_from_auth_session(session)
        token_record = _record_from_refresh_token(refresh_token)
        self._session.add(session_record)
        self._session.add(token_record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            _raise_session_integrity_error(exc)
        return _auth_session_from_record(session_record)

    async def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        """Return a session by ID, when present."""

        record = await self._session.get(AuthSessionRecord, session_id.value)
        if record is None:
            return None
        return _auth_session_from_record(record)

    async def get_active_by_id(
        self,
        session_id: SessionId,
        *,
        at: datetime,
    ) -> AuthSession | None:
        """Return a non-revoked, non-expired session by ID, when present."""

        result = await self._session.execute(
            select(AuthSessionRecord).where(
                AuthSessionRecord.id == session_id.value,
                AuthSessionRecord.revoked_at.is_(None),
                AuthSessionRecord.expires_at > at,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _auth_session_from_record(record)

    async def get_refresh_token_by_digest(
        self,
        token_digest: RefreshTokenDigest,
    ) -> RefreshTokenRecord | None:
        """Return a refresh-token record by digest, when present."""

        result = await self._session.execute(
            select(RefreshTokenRecordModel).where(
                RefreshTokenRecordModel.token_hash == token_digest.value
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return _refresh_token_from_record(record)

    async def update(self, session: AuthSession) -> AuthSession:
        """Persist session lifecycle state."""

        record = await self._session.get(AuthSessionRecord, session.id.value)
        if record is None:
            msg = "Session does not exist."
            raise SessionNotFoundError(msg)
        _update_auth_session_record(record, session)
        await self._session.flush()
        return _auth_session_from_record(record)

    async def revoke(self, session_id: SessionId, *, revoked_at: datetime) -> AuthSession:
        """Revoke one session and its current refresh credentials."""

        record = await self._session.get(AuthSessionRecord, session_id.value)
        if record is None:
            msg = "Session does not exist."
            raise SessionNotFoundError(msg)
        session = _auth_session_from_record(record).revoke(now=revoked_at)
        _update_auth_session_record(record, session)
        await self._revoke_current_refresh_tokens(session_id, revoked_at=revoked_at)
        await self._session.flush()
        return _auth_session_from_record(record)

    async def revoke_all_for_user(self, user_id: UUID, *, revoked_at: datetime) -> int:
        """Revoke all active sessions for one user and their current refresh credentials."""

        result = await self._session.execute(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.user_id == user_id,
                AuthSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, updated_at=revoked_at)
            .returning(AuthSessionRecord.id)
        )
        session_ids = [SessionId(session_id) for session_id in result.scalars()]
        for session_id in session_ids:
            await self._revoke_current_refresh_tokens(session_id, revoked_at=revoked_at)
        await self._session.flush()
        return len(session_ids)

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

        record = _record_from_refresh_token(replacement)
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            _raise_refresh_token_integrity_error(exc)

        result = await self._session.execute(
            update(RefreshTokenRecordModel)
            .where(
                RefreshTokenRecordModel.session_id == session_id.value,
                RefreshTokenRecordModel.token_hash == expected_digest.value,
                RefreshTokenRecordModel.generation == expected_generation,
                RefreshTokenRecordModel.used_at.is_(None),
                RefreshTokenRecordModel.revoked_at.is_(None),
                RefreshTokenRecordModel.replaced_by_token_id.is_(None),
                RefreshTokenRecordModel.expires_at > rotated_at,
                AuthSessionRecord.id == RefreshTokenRecordModel.session_id,
                AuthSessionRecord.revoked_at.is_(None),
                AuthSessionRecord.expires_at > rotated_at,
            )
            .values(
                used_at=rotated_at,
                replaced_by_token_id=replacement.id.value,
            )
        )
        update_result = cast(CursorResult[tuple[object, ...]], result)
        if update_result.rowcount != 1:
            await self._session.rollback()
            msg = "Refresh token rotation state is stale or invalid."
            raise RefreshRotationConflictError(msg)
        await self._session.flush()
        return _refresh_token_from_record(record)

    async def _revoke_current_refresh_tokens(
        self,
        session_id: SessionId,
        *,
        revoked_at: datetime,
    ) -> None:
        await self._session.execute(
            update(RefreshTokenRecordModel)
            .where(
                RefreshTokenRecordModel.session_id == session_id.value,
                RefreshTokenRecordModel.used_at.is_(None),
                RefreshTokenRecordModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )


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


def _record_from_password_credential(
    credential: PasswordCredential,
) -> PasswordCredentialRecord:
    return PasswordCredentialRecord(
        user_id=credential.user_id,
        password_hash=credential.password_hash,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def _password_credential_from_record(
    record: PasswordCredentialRecord,
) -> PasswordCredential:
    return PasswordCredential(
        user_id=record.user_id,
        password_hash=record.password_hash,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
    )


def _update_password_credential_record(
    record: PasswordCredentialRecord,
    credential: PasswordCredential,
) -> None:
    record.password_hash = credential.password_hash
    record.created_at = credential.created_at
    record.updated_at = credential.updated_at


def _record_from_auth_session(session: AuthSession) -> AuthSessionRecord:
    return AuthSessionRecord(
        id=session.id.value,
        user_id=session.user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
        revoked_at=session.revoked_at,
    )


def _auth_session_from_record(record: AuthSessionRecord) -> AuthSession:
    return AuthSession(
        id=SessionId(record.id),
        user_id=record.user_id,
        created_at=record.created_at.astimezone(UTC),
        updated_at=record.updated_at.astimezone(UTC),
        expires_at=record.expires_at.astimezone(UTC),
        revoked_at=record.revoked_at.astimezone(UTC) if record.revoked_at else None,
    )


def _update_auth_session_record(record: AuthSessionRecord, session: AuthSession) -> None:
    record.user_id = session.user_id
    record.created_at = session.created_at
    record.updated_at = session.updated_at
    record.expires_at = session.expires_at
    record.revoked_at = session.revoked_at


def _record_from_refresh_token(token: RefreshTokenRecord) -> RefreshTokenRecordModel:
    return RefreshTokenRecordModel(
        id=token.id.value,
        session_id=token.session_id.value,
        token_family_id=token.token_family_id.value,
        token_hash=token.token_digest.value,
        generation=token.generation,
        issued_at=token.issued_at,
        expires_at=token.expires_at,
        used_at=token.used_at,
        revoked_at=token.revoked_at,
        replaced_by_token_id=(
            token.replaced_by_token_id.value if token.replaced_by_token_id else None
        ),
    )


def _refresh_token_from_record(record: RefreshTokenRecordModel) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(record.id),
        session_id=SessionId(record.session_id),
        token_family_id=RefreshTokenFamilyId(record.token_family_id),
        token_digest=RefreshTokenDigest(record.token_hash),
        generation=record.generation,
        issued_at=record.issued_at.astimezone(UTC),
        expires_at=record.expires_at.astimezone(UTC),
        used_at=record.used_at.astimezone(UTC) if record.used_at else None,
        revoked_at=record.revoked_at.astimezone(UTC) if record.revoked_at else None,
        replaced_by_token_id=(
            RefreshTokenId(record.replaced_by_token_id) if record.replaced_by_token_id else None
        ),
    )


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


def _raise_session_integrity_error(exc: IntegrityError) -> None:
    message = str(exc.orig)
    if "uq_refresh_tokens_token_hash" in message:
        msg = "Refresh token digest already exists."
        raise DuplicateRefreshTokenDigestError(msg) from exc
    msg = "Session references a missing user."
    raise MissingIdentityReferenceError(msg) from exc


def _raise_refresh_token_integrity_error(exc: IntegrityError) -> None:
    message = str(exc.orig)
    if "uq_refresh_tokens_token_hash" in message:
        msg = "Refresh token digest already exists."
        raise DuplicateRefreshTokenDigestError(msg) from exc
    msg = "Refresh token rotation state is stale or invalid."
    raise RefreshRotationConflictError(msg) from exc

"""Identity repository integration tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from workflowforge_application.identity import (
    DuplicateNormalizedEmailError,
    DuplicateOrganizationMembershipError,
    DuplicateOrganizationSlugError,
    DuplicateRefreshTokenDigestError,
    MissingIdentityReferenceError,
    PasswordCredential,
    RefreshRotationConflictError,
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
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from workflowforge_infrastructure.identity.models import UserRecord

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_USER_ID = UUID("11111111-1111-4111-8111-222222222222")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
SECOND_ORGANIZATION_ID = UUID("22222222-2222-4222-8222-333333333333")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-444444444444")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
SECOND_SESSION_ID = UUID("44444444-4444-4444-8444-555555555555")
OTHER_USER_SESSION_ID = UUID("44444444-4444-4444-8444-666666666666")
TOKEN_ID = UUID("55555555-5555-4555-8555-555555555555")
SECOND_TOKEN_ID = UUID("55555555-5555-4555-8555-666666666666")
OTHER_TOKEN_ID = UUID("55555555-5555-4555-8555-777777777777")
REPLACEMENT_TOKEN_ID = UUID("55555555-5555-4555-8555-888888888888")
FAMILY_ID = UUID("66666666-6666-4666-8666-666666666666")
SECOND_FAMILY_ID = UUID("66666666-6666-4666-8666-777777777777")
DIGEST = "a" * 64
SECOND_DIGEST = "b" * 64
OTHER_DIGEST = "c" * 64
REPLACEMENT_DIGEST = "d" * 64


@pytest.mark.integration
async def test_user_repository_create_lookup_duplicate_and_update() -> None:
    engine, session = await _session()

    try:
        repository = SqlAlchemyUserRepository(session)
        user = _user(email=" Ada@Example.COM ")
        added = await repository.add(user)
        await session.commit()

        assert added == user
        assert await repository.get_by_id(user.id) == user
        assert await repository.get_by_normalized_email("ada@example.com") == user
        assert await repository.get_by_normalized_email(EmailAddress("ADA@example.com")) == user

        duplicate = _user(user_id=SECOND_USER_ID, email="ada@example.com")
        with pytest.raises(DuplicateNormalizedEmailError):
            await repository.add(duplicate)

        await session.rollback()
        changed = user.disable(now=NOW + timedelta(seconds=1))
        assert await repository.update(changed) == changed
        await session.commit()
        assert await repository.get_by_id(user.id) == changed
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_user_email_normalization_is_exact_and_provider_neutral() -> None:
    engine, session = await _session()

    try:
        repository = SqlAlchemyUserRepository(session)
        dotted = _user(email="first.last@gmail.com")
        plus_tagged = _user(
            user_id=SECOND_USER_ID,
            email="first.last+tag@gmail.com",
            display_name="Tagged User",
        )
        await repository.add(dotted)
        await repository.add(plus_tagged)
        await session.commit()

        assert await repository.get_by_normalized_email("first.last@gmail.com") == dotted
        assert await repository.get_by_normalized_email("firstlast@gmail.com") is None
        assert await repository.get_by_normalized_email("first.last+tag@gmail.com") == plus_tagged
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_password_credential_repository_create_retrieve_replace_and_cascade() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        credential_repo = SqlAlchemyPasswordCredentialRepository(session)
        user = await user_repo.add(_user())

        created = await credential_repo.set_for_user(
            PasswordCredential(
                user_id=user.id,
                password_hash="$argon2id$first-hash",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await session.commit()

        assert await credential_repo.get_by_user_id(user.id) == created
        assert created.password_hash == "$argon2id$first-hash"

        replaced = await credential_repo.set_for_user(
            created.replace_hash("$argon2id$replacement-hash", now=NOW + timedelta(seconds=1))
        )
        await session.commit()

        assert await credential_repo.get_by_user_id(user.id) == replaced
        assert replaced.password_hash == "$argon2id$replacement-hash"
        assert replaced.created_at == NOW
        assert replaced.updated_at == NOW + timedelta(seconds=1)

        user_record = await session.get(UserRecord, user.id)
        assert user_record is not None
        await session.delete(user_record)
        await session.commit()

        assert await credential_repo.get_by_user_id(user.id) is None
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_password_credential_repository_missing_user_rolls_back() -> None:
    engine, session = await _session()

    try:
        credential_repo = SqlAlchemyPasswordCredentialRepository(session)

        with pytest.raises(MissingIdentityReferenceError):
            await credential_repo.set_for_user(
                PasswordCredential(
                    user_id=USER_ID,
                    password_hash="$argon2id$hash",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )

        assert await credential_repo.get_by_user_id(USER_ID) is None
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_repository_create_lookup_multiple_sessions_and_duplicate_digest() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        session_repo = SqlAlchemySessionRepository(session)
        await user_repo.add(_user())

        first = _auth_session()
        second = _auth_session(session_id=SECOND_SESSION_ID)
        await session_repo.add(session=first, refresh_token=_refresh_token())
        await session_repo.add(
            session=second,
            refresh_token=_refresh_token(
                token_id=SECOND_TOKEN_ID,
                session_id=SECOND_SESSION_ID,
                family_id=SECOND_FAMILY_ID,
                digest=SECOND_DIGEST,
            ),
        )
        await session.commit()

        assert await session_repo.get_by_id(SessionId(SESSION_ID)) == first
        assert await session_repo.get_active_by_id(SessionId(SESSION_ID), at=NOW) == first
        assert (
            await session_repo.get_refresh_token_by_digest(RefreshTokenDigest(DIGEST))
            == _refresh_token()
        )

        duplicate = _auth_session(session_id=UUID("44444444-4444-4444-8444-777777777777"))
        with pytest.raises(DuplicateRefreshTokenDigestError):
            await session_repo.add(
                session=duplicate,
                refresh_token=_refresh_token(
                    token_id=OTHER_TOKEN_ID,
                    session_id=duplicate.id.value,
                    family_id=UUID("66666666-6666-4666-8666-888888888888"),
                    digest=DIGEST,
                ),
            )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_repository_revoke_one_and_revoke_all_for_user() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        session_repo = SqlAlchemySessionRepository(session)
        await user_repo.add(_user())
        await user_repo.add(
            _user(
                user_id=SECOND_USER_ID,
                email="grace@example.com",
                display_name="Grace Hopper",
            )
        )
        await session_repo.add(session=_auth_session(), refresh_token=_refresh_token())
        await session_repo.add(
            session=_auth_session(session_id=SECOND_SESSION_ID),
            refresh_token=_refresh_token(
                token_id=SECOND_TOKEN_ID,
                session_id=SECOND_SESSION_ID,
                family_id=SECOND_FAMILY_ID,
                digest=SECOND_DIGEST,
            ),
        )
        other_user_session = _auth_session(
            session_id=OTHER_USER_SESSION_ID,
            user_id=SECOND_USER_ID,
        )
        await session_repo.add(
            session=other_user_session,
            refresh_token=_refresh_token(
                token_id=OTHER_TOKEN_ID,
                session_id=OTHER_USER_SESSION_ID,
                family_id=UUID("66666666-6666-4666-8666-999999999999"),
                digest=OTHER_DIGEST,
            ),
        )
        await session.commit()

        revoked = await session_repo.revoke(
            SessionId(SESSION_ID),
            revoked_at=NOW + timedelta(minutes=1),
        )
        assert revoked.revoked_at == NOW + timedelta(minutes=1)
        assert await session_repo.get_active_by_id(SessionId(SESSION_ID), at=NOW) is None

        affected = await session_repo.revoke_all_for_user(
            USER_ID,
            revoked_at=NOW + timedelta(minutes=2),
        )
        await session.commit()

        assert affected == 1
        assert await session_repo.get_active_by_id(SessionId(SECOND_SESSION_ID), at=NOW) is None
        assert (
            await session_repo.get_active_by_id(SessionId(OTHER_USER_SESSION_ID), at=NOW)
            == other_user_session
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_repository_refresh_rotation_is_compare_and_swap_safe() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        session_repo = SqlAlchemySessionRepository(session)
        await user_repo.add(_user())
        await session_repo.add(session=_auth_session(), refresh_token=_refresh_token())
        await session.commit()

        replacement = _refresh_token(
            token_id=REPLACEMENT_TOKEN_ID,
            digest=REPLACEMENT_DIGEST,
            generation=1,
            issued_at=NOW + timedelta(minutes=5),
            expires_at=NOW + timedelta(hours=2),
        )
        rotated = await session_repo.rotate_refresh_token(
            session_id=SessionId(SESSION_ID),
            expected_digest=RefreshTokenDigest(DIGEST),
            expected_generation=0,
            replacement=replacement,
            rotated_at=NOW + timedelta(minutes=5),
        )
        await session.commit()

        assert rotated == replacement
        consumed = await session_repo.get_refresh_token_by_digest(RefreshTokenDigest(DIGEST))
        assert consumed is not None
        assert consumed.used_at == NOW + timedelta(minutes=5)
        assert consumed.replaced_by_token_id == RefreshTokenId(REPLACEMENT_TOKEN_ID)

        with pytest.raises(RefreshRotationConflictError):
            await session_repo.rotate_refresh_token(
                session_id=SessionId(SESSION_ID),
                expected_digest=RefreshTokenDigest(DIGEST),
                expected_generation=0,
                replacement=_refresh_token(
                    token_id=UUID("55555555-5555-4555-8555-999999999999"),
                    digest="e" * 64,
                    generation=1,
                    issued_at=NOW + timedelta(minutes=6),
                    expires_at=NOW + timedelta(hours=2),
                ),
                rotated_at=NOW + timedelta(minutes=6),
            )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_repository_expired_and_revoked_sessions_cannot_rotate() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        session_repo = SqlAlchemySessionRepository(session)
        await user_repo.add(_user())
        expired = _auth_session(
            expires_at=NOW + timedelta(minutes=1),
        )
        await session_repo.add(session=expired, refresh_token=_refresh_token())
        await session.commit()

        with pytest.raises(RefreshRotationConflictError):
            await session_repo.rotate_refresh_token(
                session_id=SessionId(SESSION_ID),
                expected_digest=RefreshTokenDigest(DIGEST),
                expected_generation=0,
                replacement=_refresh_token(
                    token_id=REPLACEMENT_TOKEN_ID,
                    digest=REPLACEMENT_DIGEST,
                    generation=1,
                    issued_at=NOW + timedelta(minutes=2),
                    expires_at=NOW + timedelta(hours=2),
                ),
                rotated_at=NOW + timedelta(minutes=2),
            )

        await session.rollback()
        await session_repo.revoke(SessionId(SESSION_ID), revoked_at=NOW + timedelta(seconds=30))
        await session.commit()

        with pytest.raises(RefreshRotationConflictError):
            await session_repo.rotate_refresh_token(
                session_id=SessionId(SESSION_ID),
                expected_digest=RefreshTokenDigest(DIGEST),
                expected_generation=0,
                replacement=_refresh_token(
                    token_id=REPLACEMENT_TOKEN_ID,
                    digest=REPLACEMENT_DIGEST,
                    generation=1,
                    issued_at=NOW + timedelta(seconds=40),
                    expires_at=NOW + timedelta(hours=2),
                ),
                rotated_at=NOW + timedelta(seconds=40),
            )
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_session_repository_transaction_rollback_and_user_delete_cascade() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        session_repo = SqlAlchemySessionRepository(session)
        user = await user_repo.add(_user())
        await session_repo.add(session=_auth_session(), refresh_token=_refresh_token())

        await session.rollback()
        assert await session_repo.get_by_id(SessionId(SESSION_ID)) is None

        await user_repo.add(user)
        await session_repo.add(session=_auth_session(), refresh_token=_refresh_token())
        await session.commit()

        user_record = await session.get(UserRecord, user.id)
        assert user_record is not None
        await session.delete(user_record)
        await session.commit()

        assert await session_repo.get_by_id(SessionId(SESSION_ID)) is None
        assert await session_repo.get_refresh_token_by_digest(RefreshTokenDigest(DIGEST)) is None
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_organization_repository_create_lookup_duplicate_update_and_list() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        organization_repo = SqlAlchemyOrganizationRepository(session)
        membership_repo = SqlAlchemyMembershipRepository(session)
        user = await user_repo.add(_user())
        organization = await organization_repo.add(_organization())
        await membership_repo.add(_active_membership(role=Role.OWNER))
        await session.commit()

        assert await organization_repo.get_by_id(organization.id) == organization
        found_by_slug = await organization_repo.get_by_slug(OrganizationSlug("workflow-forge"))
        assert found_by_slug == organization
        assert await organization_repo.list_for_user(user.id) == [organization]

        duplicate = _organization(
            organization_id=SECOND_ORGANIZATION_ID,
            slug=OrganizationSlug("workflow-forge"),
        )
        with pytest.raises(DuplicateOrganizationSlugError):
            await organization_repo.add(duplicate)

        await session.rollback()
        renamed = organization.rename("Renamed Forge", now=NOW + timedelta(seconds=1))
        assert await organization_repo.update(renamed) == renamed
        await session.commit()
        assert await organization_repo.get_by_id(organization.id) == renamed
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_membership_repository_tenant_scoped_behavior_and_duplicates() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        organization_repo = SqlAlchemyOrganizationRepository(session)
        membership_repo = SqlAlchemyMembershipRepository(session)

        await user_repo.add(_user())
        await organization_repo.add(_organization())
        await organization_repo.add(
            _organization(
                organization_id=SECOND_ORGANIZATION_ID,
                name="Second Organization",
                slug=OrganizationSlug("second-org"),
            )
        )
        active = await membership_repo.add(_active_membership(role=Role.OWNER))
        other_org_membership = await membership_repo.add(
            _active_membership(
                membership_id=SECOND_MEMBERSHIP_ID,
                organization_id=SECOND_ORGANIZATION_ID,
                role=Role.ADMIN,
            )
        )
        await session.commit()

        assert (
            await membership_repo.get_by_id(
                organization_id=ORGANIZATION_ID,
                membership_id=active.id,
            )
            == active
        )
        assert (
            await membership_repo.get_by_id(
                organization_id=SECOND_ORGANIZATION_ID,
                membership_id=active.id,
            )
            is None
        )
        assert (
            await membership_repo.get_by_user_and_organization(
                user_id=USER_ID,
                organization_id=ORGANIZATION_ID,
            )
            == active
        )
        assert (
            await membership_repo.get_by_user_and_organization(
                user_id=USER_ID,
                organization_id=SECOND_ORGANIZATION_ID,
            )
            == other_org_membership
        )
        assert await membership_repo.list_for_organization(ORGANIZATION_ID) == [active]
        assert await membership_repo.list_for_user(USER_ID) == [active, other_org_membership]

        suspended_other_org = other_org_membership.suspend(now=NOW + timedelta(seconds=1))
        assert await membership_repo.update(suspended_other_org) == suspended_other_org
        await session.commit()
        assert (
            await membership_repo.get_by_user_and_organization(
                user_id=USER_ID,
                organization_id=SECOND_ORGANIZATION_ID,
            )
            == suspended_other_org
        )
        assert (
            await membership_repo.get_by_user_and_organization(
                user_id=USER_ID,
                organization_id=ORGANIZATION_ID,
            )
            == active
        )

        duplicate = _active_membership(
            membership_id=UUID("33333333-3333-4333-8333-555555555555"),
            role=Role.OWNER,
        )
        with pytest.raises(DuplicateOrganizationMembershipError):
            await membership_repo.add(duplicate)
    finally:
        await session.close()
        await dispose_async_engine(engine)


@pytest.mark.integration
async def test_membership_repository_invited_update_and_missing_foreign_key() -> None:
    engine, session = await _session()

    try:
        user_repo = SqlAlchemyUserRepository(session)
        organization_repo = SqlAlchemyOrganizationRepository(session)
        membership_repo = SqlAlchemyMembershipRepository(session)

        await user_repo.add(_user())
        await organization_repo.add(_organization())
        invited = await membership_repo.add(_invited_membership())
        await session.commit()

        assert invited.status is MembershipStatus.INVITED
        assert invited.invited_at == NOW
        assert invited.joined_at is None

        activated = invited.activate(now=NOW + timedelta(seconds=1))
        assert await membership_repo.update(activated) == activated
        await session.commit()
        assert (
            await membership_repo.get_by_user_and_organization(
                user_id=USER_ID,
                organization_id=ORGANIZATION_ID,
            )
            == activated
        )

        missing_user = _active_membership(
            membership_id=SECOND_MEMBERSHIP_ID,
            user_id=SECOND_USER_ID,
            role=Role.ADMIN,
        )
        with pytest.raises(MissingIdentityReferenceError):
            await membership_repo.add(missing_user)
    finally:
        await session.close()
        await dispose_async_engine(engine)


async def _session() -> tuple[AsyncEngine, AsyncSession]:
    settings = require_postgresql()
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")
    engine = create_async_database_engine(settings)
    session = create_async_session_factory(engine)()
    return engine, session


def _user(
    *,
    user_id: UUID = USER_ID,
    email: str = "ada@example.com",
    display_name: str = "Ada Lovelace",
) -> User:
    return User.create(
        id=user_id,
        email=EmailAddress(email),
        display_name=display_name,
        now=NOW,
    )


def _organization(
    *,
    organization_id: UUID = ORGANIZATION_ID,
    name: str = "WorkflowForge",
    slug: OrganizationSlug | None = None,
) -> Organization:
    return Organization.create(
        id=organization_id,
        name=name,
        slug=slug or OrganizationSlug("workflow-forge"),
        now=NOW,
    )


def _active_membership(
    *,
    membership_id: UUID = MEMBERSHIP_ID,
    user_id: UUID = USER_ID,
    organization_id: UUID = ORGANIZATION_ID,
    role: Role,
) -> Membership:
    return Membership.activate_directly(
        id=membership_id,
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        now=NOW,
    )


def _auth_session(
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    expires_at: datetime = NOW + timedelta(hours=1),
) -> AuthSession:
    return AuthSession.create(
        id=SessionId(session_id),
        user_id=user_id,
        now=NOW,
        expires_at=expires_at,
    )


def _refresh_token(
    *,
    token_id: UUID = TOKEN_ID,
    session_id: UUID = SESSION_ID,
    family_id: UUID = FAMILY_ID,
    digest: str = DIGEST,
    generation: int = 0,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=1),
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=RefreshTokenId(token_id),
        session_id=SessionId(session_id),
        token_family_id=RefreshTokenFamilyId(family_id),
        token_digest=RefreshTokenDigest(digest),
        generation=generation,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _invited_membership() -> Membership:
    return Membership.invite(
        id=MEMBERSHIP_ID,
        user_id=USER_ID,
        organization_id=ORGANIZATION_ID,
        role=Role.ADMIN,
        now=NOW,
    )


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

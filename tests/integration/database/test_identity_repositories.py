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
    MissingIdentityReferenceError,
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
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyUserRepository,
)

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_USER_ID = UUID("11111111-1111-4111-8111-222222222222")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
SECOND_ORGANIZATION_ID = UUID("22222222-2222-4222-8222-333333333333")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-444444444444")


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
        assert await membership_repo.list_for_organization(ORGANIZATION_ID) == [active]
        assert await membership_repo.list_for_user(USER_ID) == [active, other_org_membership]

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

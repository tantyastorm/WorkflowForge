"""Tenant context API integration tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_application.identity import SetUserPassword, SetUserPasswordCommand
from workflowforge_domain.identity import (
    EmailAddress,
    Membership,
    Organization,
    OrganizationSlug,
    Role,
    User,
)
from workflowforge_infrastructure.config import Environment, Settings
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    Argon2PasswordHasher,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemyUserRepository,
)

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
PASSWORD = "correct horse battery staple"
USER_A_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_B_ID = UUID("11111111-1111-4111-8111-222222222222")
ORG_A_ID = UUID("22222222-2222-4222-8222-222222222222")
ORG_B_ID = UUID("22222222-2222-4222-8222-333333333333")
MEMBERSHIP_A_ID = UUID("33333333-3333-4333-8333-333333333333")
MEMBERSHIP_B_ID = UUID("33333333-3333-4333-8333-444444444444")


@pytest.mark.integration
def test_tenant_context_http_flow_enforces_cross_tenant_isolation() -> None:
    settings = _settings()
    _reset_database()
    _seed_base_identities(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        login_a = _login(client, "ada@example.com")
        access_a = login_a["access_token"]

        missing_selector = client.get(
            "/api/v1/organizations/not-a-uuid/tenancy/context",
            headers=_bearer(access_a),
        )
        org_a_context = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        org_a_probe = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/authorized-probe",
            headers=_bearer(access_a),
        )
        org_b_without_membership = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/context",
            headers=_bearer(access_a),
            params={"membership_id": str(MEMBERSHIP_A_ID), "role": "owner"},
        )

        assert missing_selector.status_code == 422
        assert org_a_context.status_code == 200
        assert org_a_context.json()["organization_id"] == str(ORG_A_ID)
        assert org_a_context.json()["membership_id"] == str(MEMBERSHIP_A_ID)
        assert org_a_context.json()["role"] == "owner"
        assert "security.manage" in org_a_context.json()["permissions"]
        assert org_a_probe.status_code == 200
        assert org_b_without_membership.status_code == 403
        assert org_b_without_membership.json()["error"]["code"] == "tenant_access_denied"

        _create_org_b_membership(settings)
        invited_b = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        assert invited_b.status_code == 403

        _activate_org_b_membership(settings)
        org_b_context = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        org_b_probe_denied = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/authorized-probe",
            headers=_bearer(access_a),
            params={"role": "owner", "permissions": "security.manage"},
        )
        assert org_b_context.status_code == 200
        assert org_b_context.json()["organization_id"] == str(ORG_B_ID)
        assert org_b_context.json()["membership_id"] == str(MEMBERSHIP_B_ID)
        assert org_b_context.json()["role"] == "auditor"
        assert "audit.read" in org_b_context.json()["permissions"]
        assert org_b_probe_denied.status_code == 403
        assert org_b_probe_denied.json()["error"]["code"] == "permission_denied"

        _suspend_org_b_membership(settings)
        suspended_b = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/context",
            headers=_bearer(access_a),
            params={"membership_id": str(MEMBERSHIP_A_ID)},
        )
        org_a_still_available = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        assert suspended_b.status_code == 403
        assert org_a_still_available.status_code == 200
        assert org_a_still_available.json()["organization_id"] == str(ORG_A_ID)

        _remove_org_b_membership(settings)
        removed_b = client.get(
            f"/api/v1/organizations/{ORG_B_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        assert removed_b.status_code == 403
        assert removed_b.json()["error"]["code"] == "tenant_access_denied"

        login_b = _login(client, "grace@example.com")
        user_b_org_a = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/context",
            headers=_bearer(login_b["access_token"]),
        )
        assert user_b_org_a.status_code == 403

        _deactivate_org_a(settings)
        inactive_org_a = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        assert inactive_org_a.status_code == 403
        assert inactive_org_a.json()["error"]["code"] == "tenant_access_denied"

        logout = client.post(
            "/api/v1/auth/logout",
            headers={
                **_bearer(access_a),
                "X-CSRF-Token": login_a["csrf_token"],
                "Cookie": (
                    f"workflowforge_refresh={login_a['refresh_token']}; "
                    f"workflowforge_csrf={login_a['csrf_token']}"
                ),
            },
        )
        revoked_context = client.get(
            f"/api/v1/organizations/{ORG_A_ID}/tenancy/context",
            headers=_bearer(access_a),
        )
        assert logout.status_code == 200
        assert revoked_context.status_code == 401
        assert revoked_context.headers["www-authenticate"] == "Bearer"


def _settings() -> Settings:
    return Settings(environment=Environment.TEST, database=require_postgresql())


def _reset_database() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")


def _seed_base_identities(settings: Settings) -> None:
    asyncio.run(_seed_base_identities_async(settings))


async def _seed_base_identities_async(settings: Settings) -> None:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        users = SqlAlchemyUserRepository(session)
        organizations = SqlAlchemyOrganizationRepository(session)
        memberships = SqlAlchemyMembershipRepository(session)
        credentials = SqlAlchemyPasswordCredentialRepository(session)
        hasher = Argon2PasswordHasher()
        await users.add(_user(USER_A_ID, email="ada@example.com", name="Ada Lovelace"))
        await users.add(_user(USER_B_ID, email="grace@example.com", name="Grace Hopper"))
        await organizations.add(_organization(ORG_A_ID, slug="org-a"))
        await organizations.add(_organization(ORG_B_ID, slug="org-b"))
        await memberships.add(
            Membership.activate_directly(
                id=MEMBERSHIP_A_ID,
                user_id=USER_A_ID,
                organization_id=ORG_A_ID,
                role=Role.OWNER,
                now=NOW,
            )
        )
        set_password = SetUserPassword(
            users=users,
            credentials=credentials,
            password_hasher=hasher,
        )
        await set_password(SetUserPasswordCommand(user_id=USER_A_ID, password=PASSWORD), now=NOW)
        await set_password(SetUserPasswordCommand(user_id=USER_B_ID, password=PASSWORD), now=NOW)
        await session.commit()
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _create_org_b_membership(settings: Settings) -> None:
    asyncio.run(_create_org_b_membership_async(settings))


async def _create_org_b_membership_async(settings: Settings) -> None:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        memberships = SqlAlchemyMembershipRepository(session)
        await memberships.add(
            Membership.invite(
                id=MEMBERSHIP_B_ID,
                user_id=USER_A_ID,
                organization_id=ORG_B_ID,
                role=Role.AUDITOR,
                now=NOW + timedelta(minutes=1),
            )
        )
        await session.commit()
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _activate_org_b_membership(settings: Settings) -> None:
    asyncio.run(_mutate_org_b_membership(settings, "activate"))


def _suspend_org_b_membership(settings: Settings) -> None:
    asyncio.run(_mutate_org_b_membership(settings, "suspend"))


def _remove_org_b_membership(settings: Settings) -> None:
    asyncio.run(_mutate_org_b_membership(settings, "remove"))


async def _mutate_org_b_membership(settings: Settings, mutation: str) -> None:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        memberships = SqlAlchemyMembershipRepository(session)
        membership = await memberships.get_by_user_and_organization(
            user_id=USER_A_ID,
            organization_id=ORG_B_ID,
        )
        assert membership is not None
        if mutation == "activate":
            changed = membership.activate(now=NOW + timedelta(minutes=2))
        elif mutation == "suspend":
            changed = membership.suspend(now=NOW + timedelta(minutes=3))
        elif mutation == "remove":
            changed = membership.remove(now=NOW + timedelta(minutes=4))
        else:
            raise AssertionError(mutation)
        await memberships.update(changed)
        await session.commit()
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _deactivate_org_a(settings: Settings) -> None:
    asyncio.run(_deactivate_org_a_async(settings))


async def _deactivate_org_a_async(settings: Settings) -> None:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        organizations = SqlAlchemyOrganizationRepository(session)
        organization = await organizations.get_by_id(ORG_A_ID)
        assert organization is not None
        await organizations.update(organization.deactivate(now=NOW + timedelta(minutes=5)))
        await session.commit()
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return {
        "access_token": response.json()["access_token"],
        "refresh_token": response.cookies["workflowforge_refresh"],
        "csrf_token": response.cookies["workflowforge_csrf"],
    }


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _user(user_id: UUID, *, email: str, name: str) -> User:
    return User.create(
        id=user_id,
        email=EmailAddress(email),
        display_name=name,
        now=NOW,
    )


def _organization(organization_id: UUID, *, slug: str) -> Organization:
    return Organization.create(
        id=organization_id,
        name=slug.upper(),
        slug=OrganizationSlug(slug),
        now=NOW,
    )


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config

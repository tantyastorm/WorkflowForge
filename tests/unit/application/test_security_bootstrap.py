"""Security bootstrap use-case tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from workflowforge_application.identity import PasswordCredential
from workflowforge_application.security import (
    BootstrapOwner,
    BootstrapOwnerCommand,
    BootstrapRefusedError,
    BootstrapState,
)
from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome
from workflowforge_domain.identity import Membership, MembershipStatus, Organization, Role, User

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
AUDIT_ID = UUID("44444444-4444-4444-8444-444444444444")


@pytest.mark.asyncio
async def test_bootstrap_owner_creates_first_owner_membership_password_and_audit() -> None:
    state = FakeBootstrapRepository(BootstrapState(users=0, organizations=0))
    users = FakeUsers()
    organizations = FakeOrganizations()
    memberships = FakeMemberships()
    credentials = FakeCredentials()
    audit = FakeAudit()
    transaction = FakeTransaction()
    use_case = BootstrapOwner(
        state=state,
        users=users,
        organizations=organizations,
        memberships=memberships,
        credentials=credentials,
        password_hasher=FakePasswordHasher(),
        audit=audit,
        transaction=transaction,
        ids=FakeIds([USER_ID, ORG_ID, MEMBERSHIP_ID, AUDIT_ID]),
    )

    result = await use_case(
        BootstrapOwnerCommand(
            email="Ada@Example.COM",
            display_name="Ada Lovelace",
            password="correct horse battery staple",
            organization_name="Acme Automation",
            organization_slug="acme",
        )
    )

    assert result.user_id == USER_ID
    assert result.organization_id == ORG_ID
    assert result.membership_id == MEMBERSHIP_ID
    assert state.locked is True
    assert users.items[0].email.normalized == "ada@example.com"
    assert organizations.items[0].slug.value == "acme"
    assert memberships.items[0].role is Role.OWNER
    assert memberships.items[0].status is MembershipStatus.ACTIVE
    assert credentials.items[0].user_id == USER_ID
    assert credentials.items[0].password_hash == "hashed:correct horse battery staple"
    assert audit.events[0].event_type is AuditEventType.BOOTSTRAP_OWNER_CREATED
    assert audit.events[0].outcome is AuditOutcome.SUCCESS
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_bootstrap_owner_refuses_existing_identity_state_and_audits() -> None:
    transaction = FakeTransaction()
    audit = FakeAudit()
    use_case = BootstrapOwner(
        state=FakeBootstrapRepository(BootstrapState(users=1, organizations=0)),
        users=FakeUsers(),
        organizations=FakeOrganizations(),
        memberships=FakeMemberships(),
        credentials=FakeCredentials(),
        password_hasher=FakePasswordHasher(),
        audit=audit,
        transaction=transaction,
        ids=FakeIds([AUDIT_ID]),
    )

    with pytest.raises(BootstrapRefusedError):
        await use_case(
            BootstrapOwnerCommand(
                email="owner@example.com",
                display_name="Owner",
                password="correct horse battery staple",
                organization_name="Existing",
                organization_slug="existing",
            )
        )

    assert audit.events[0].event_type is AuditEventType.BOOTSTRAP_REFUSED
    assert audit.events[0].outcome is AuditOutcome.DENIED
    assert audit.events[0].metadata == {"users": 1, "organizations": 0}
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


class FakeBootstrapRepository:
    def __init__(self, state: BootstrapState) -> None:
        self.state = state
        self.locked = False

    async def acquire_bootstrap_lock(self) -> None:
        self.locked = True

    async def bootstrap_state(self) -> BootstrapState:
        return self.state


class FakeUsers:
    def __init__(self) -> None:
        self.items: list[User] = []

    async def add(self, user: User) -> User:
        self.items.append(user)
        return user

    async def get_by_id(self, _user_id: UUID) -> User | None:
        return next((user for user in self.items if user.id == _user_id), None)

    async def get_by_normalized_email(self, _email: object) -> User | None:
        return None

    async def update(self, user: User) -> User:
        return user


class FakeOrganizations:
    def __init__(self) -> None:
        self.items: list[Organization] = []

    async def add(self, organization: Organization) -> Organization:
        self.items.append(organization)
        return organization

    async def get_by_id(self, _organization_id: UUID) -> Organization | None:
        return None

    async def get_by_slug(self, _slug: object) -> Organization | None:
        return None

    async def list_for_user(self, _user_id: UUID) -> list[Organization]:
        return []

    async def update(self, organization: Organization) -> Organization:
        return organization


class FakeMemberships:
    def __init__(self) -> None:
        self.items: list[Membership] = []

    async def add(self, membership: Membership) -> Membership:
        self.items.append(membership)
        return membership

    async def get_by_id(self, *, organization_id: UUID, membership_id: UUID) -> None:
        return None

    async def get_by_user_and_organization(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> None:
        return None

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        return []

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        return []

    async def update(self, membership: Membership) -> Membership:
        return membership


class FakeCredentials:
    def __init__(self) -> None:
        self.items: list[PasswordCredential] = []

    async def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        return None

    async def set_for_user(self, credential: PasswordCredential) -> PasswordCredential:
        self.items.append(credential)
        return credential


class FakePasswordHasher:
    def hash_password(self, plain_password: str) -> str:
        return f"hashed:{plain_password}"

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{plain_password}"

    def dummy_password_hash(self) -> str:
        return "hashed:dummy"


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeIds:
    def __init__(self, ids: list[UUID]) -> None:
        self.ids = ids

    def new_uuid(self) -> UUID:
        return self.ids.pop(0)

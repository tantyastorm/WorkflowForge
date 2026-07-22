"""Authorization application policy tests."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from workflowforge_application.authorization import (
    AuthorizationPolicy,
    MembershipAdministrationDenied,
    MembershipAdministrationMutation,
    MembershipAdministrationPolicy,
    PermissionDenied,
    ResolveTenantContext,
    ResolveTenantContextCommand,
    TenantAccessDenied,
    TenantBoundaryViolation,
    TenantContext,
    TenantMembershipInactive,
    ensure_self_role_change_allowed,
)
from workflowforge_application.identity import MembershipRepository, OrganizationRepository
from workflowforge_domain.identity import (
    InvalidIdentifier,
    LastActiveOwnerViolation,
    Membership,
    MembershipStatus,
    Organization,
    OrganizationSlug,
    Permission,
    Role,
    permissions_for_role,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_ORG_ID = UUID("99999999-9999-4999-8999-999999999999")


def test_tenant_context_creation_resolves_role_permissions() -> None:
    context = _context(role=Role.ADMIN)

    assert context.user_id == _user_id(1)
    assert context.organization_id == ORG_ID
    assert context.membership_id == _membership_id(1)
    assert context.role is Role.ADMIN
    assert context.permissions == permissions_for_role(Role.ADMIN)
    assert "permissions=frozenset" in repr(context)


def test_tenant_context_is_immutable_and_rejects_nil_identifiers() -> None:
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.role = Role.OWNER  # type: ignore[misc]

    with pytest.raises(InvalidIdentifier, match="nil UUID"):
        TenantContext.create(
            user_id=UUID(int=0),
            organization_id=ORG_ID,
            membership_id=_membership_id(1),
            role=Role.ADMIN,
        )


def test_tenant_context_normal_construction_resolves_permissions() -> None:
    context = TenantContext(
        user_id=_user_id(1),
        organization_id=ORG_ID,
        membership_id=_membership_id(1),
        role=Role.AUDITOR,
    )

    assert context.permissions == permissions_for_role(Role.AUDITOR)


def test_tenant_context_trusted_factory_normalizes_permission_collections() -> None:
    trusted = TenantContext.trusted_with_permissions(
        user_id=_user_id(1),
        organization_id=ORG_ID,
        membership_id=_membership_id(1),
        role=Role.ADMIN,
        permissions=[Permission.ORGANIZATION_READ],
    )

    assert trusted.permissions == frozenset({Permission.ORGANIZATION_READ})

    with pytest.raises(TypeError):
        TenantContext(
            user_id=_user_id(1),
            organization_id=ORG_ID,
            membership_id=_membership_id(1),
            role=Role.ADMIN,
            permissions=[Permission.ORGANIZATION_READ],  # type: ignore[call-arg]
        )

    with pytest.raises(TypeError, match="Permission"):
        TenantContext.trusted_with_permissions(
            user_id=_user_id(1),
            organization_id=ORG_ID,
            membership_id=_membership_id(1),
            role=Role.ADMIN,
            permissions=["organization.read"],  # type: ignore[list-item]
        )


def test_authorization_policy_allows_and_requires_permissions() -> None:
    policy = AuthorizationPolicy()
    context = _context(role=Role.ADMIN)

    assert policy.allows(context, Permission.MEMBERSHIP_UPDATE) is True
    assert policy.allows(context, Permission.SECURITY_MANAGE) is False
    policy.require(context, Permission.MEMBERSHIP_UPDATE)

    with pytest.raises(PermissionDenied) as exc_info:
        policy.require(context, Permission.SECURITY_MANAGE)

    error = exc_info.value
    assert error.user_id == context.user_id
    assert error.organization_id == context.organization_id
    assert error.permission is Permission.SECURITY_MANAGE
    assert str(context.user_id) in str(error)
    assert Permission.SECURITY_MANAGE.value in str(error)


def test_authorization_policy_any_and_all_permissions() -> None:
    policy = AuthorizationPolicy()
    auditor_context = _context(role=Role.AUDITOR)

    policy.require_any(
        auditor_context,
        (Permission.AUDIT_READ, Permission.SECURITY_MANAGE),
    )
    policy.require_all(
        auditor_context,
        (Permission.ORGANIZATION_READ, Permission.MEMBERSHIP_READ),
    )

    with pytest.raises(PermissionDenied):
        policy.require_any(
            auditor_context,
            (Permission.SECURITY_MANAGE, Permission.API_KEYS_MANAGE),
        )

    with pytest.raises(PermissionDenied):
        policy.require_all(
            auditor_context,
            (Permission.ORGANIZATION_READ, Permission.SECURITY_MANAGE),
        )

    with pytest.raises(ValueError):
        policy.require_any(auditor_context, ())


@pytest.mark.asyncio
async def test_tenant_context_resolver_returns_active_membership_context() -> None:
    membership = _membership(1, role=Role.ADMIN)
    resolver = ResolveTenantContext(
        organizations=_organization_repository({ORG_ID: _organization()}),
        memberships=_membership_repository(
            {(membership.user_id, membership.organization_id): membership}
        ),
    )

    context = await resolver(
        ResolveTenantContextCommand(
            user_id=membership.user_id,
            organization_id=membership.organization_id,
        )
    )

    assert context.user_id == membership.user_id
    assert context.organization_id == membership.organization_id
    assert context.membership_id == membership.id
    assert context.role is Role.ADMIN
    assert context.permissions == permissions_for_role(Role.ADMIN)


@pytest.mark.asyncio
async def test_tenant_context_resolver_rejects_missing_or_inactive_tenant_state() -> None:
    active_membership = _membership(1, role=Role.OWNER)
    invited = _membership(2, role=Role.ADMIN, status=MembershipStatus.INVITED)
    suspended = _membership(3, role=Role.ADMIN, status=MembershipStatus.SUSPENDED)
    removed = _membership(4, role=Role.ADMIN, status=MembershipStatus.REMOVED)
    inactive_organization = _organization().deactivate(now=NOW)

    missing_org_resolver = ResolveTenantContext(
        organizations=_organization_repository({}),
        memberships=_membership_repository({}),
    )
    with pytest.raises(TenantAccessDenied, match="organization not found"):
        await missing_org_resolver(
            ResolveTenantContextCommand(user_id=_user_id(1), organization_id=ORG_ID)
        )

    inactive_org_resolver = ResolveTenantContext(
        organizations=_organization_repository({ORG_ID: inactive_organization}),
        memberships=_membership_repository(
            {(active_membership.user_id, ORG_ID): active_membership}
        ),
    )
    with pytest.raises(TenantAccessDenied, match="organization inactive"):
        await inactive_org_resolver(
            ResolveTenantContextCommand(user_id=active_membership.user_id, organization_id=ORG_ID)
        )

    missing_membership_resolver = ResolveTenantContext(
        organizations=_organization_repository({ORG_ID: _organization()}),
        memberships=_membership_repository({}),
    )
    with pytest.raises(TenantAccessDenied, match="membership not found"):
        await missing_membership_resolver(
            ResolveTenantContextCommand(user_id=_user_id(1), organization_id=ORG_ID)
        )

    for membership in (invited, suspended, removed):
        resolver = ResolveTenantContext(
            organizations=_organization_repository({ORG_ID: _organization()}),
            memberships=_membership_repository({(membership.user_id, ORG_ID): membership}),
        )
        with pytest.raises(TenantMembershipInactive) as exc_info:
            await resolver(
                ResolveTenantContextCommand(
                    user_id=membership.user_id,
                    organization_id=ORG_ID,
                )
            )
        assert exc_info.value.status is membership.status


@pytest.mark.asyncio
async def test_tenant_context_resolver_keeps_organizations_distinct() -> None:
    membership_a = _membership(1, role=Role.OPERATOR, organization_id=ORG_ID)
    membership_b = _membership(2, role=Role.AUDITOR, organization_id=OTHER_ORG_ID)
    suspended_b = _membership(
        3,
        role=Role.OWNER,
        organization_id=OTHER_ORG_ID,
        status=MembershipStatus.SUSPENDED,
    )

    resolver = ResolveTenantContext(
        organizations=_organization_repository(
            {
                ORG_ID: _organization(),
                OTHER_ORG_ID: _organization(organization_id=OTHER_ORG_ID),
            }
        ),
        memberships=_membership_repository(
            {
                (membership_a.user_id, ORG_ID): membership_a,
                (membership_a.user_id, OTHER_ORG_ID): membership_b,
                (suspended_b.user_id, OTHER_ORG_ID): suspended_b,
            }
        ),
    )

    context_a = await resolver(
        ResolveTenantContextCommand(user_id=membership_a.user_id, organization_id=ORG_ID)
    )
    context_b = await resolver(
        ResolveTenantContextCommand(
            user_id=membership_a.user_id,
            organization_id=OTHER_ORG_ID,
        )
    )

    assert context_a.organization_id == ORG_ID
    assert context_a.role is Role.OPERATOR
    assert context_b.organization_id == OTHER_ORG_ID
    assert context_b.role is Role.AUDITOR
    with pytest.raises(TenantMembershipInactive):
        await resolver(
            ResolveTenantContextCommand(
                user_id=suspended_b.user_id,
                organization_id=OTHER_ORG_ID,
            )
        )
    assert (
        await resolver(
            ResolveTenantContextCommand(user_id=membership_a.user_id, organization_id=ORG_ID)
        )
    ).role is Role.OPERATOR


def test_permission_denial_is_distinct_from_membership_target_restriction() -> None:
    policy = AuthorizationPolicy()
    operator_context = _context(role=Role.OPERATOR)

    with pytest.raises(PermissionDenied):
        policy.require(operator_context, Permission.MEMBERSHIP_UPDATE)

    admin = _membership(1, role=Role.ADMIN)
    owner = _membership(2, role=Role.OWNER)

    with pytest.raises(MembershipAdministrationDenied):
        MembershipAdministrationPolicy.ensure_target_manageable(
            actor_membership=admin,
            target_membership=owner,
            mutation=MembershipAdministrationMutation.UPDATE,
        )


def test_membership_policy_owner_manages_non_owner_and_promotes_to_owner() -> None:
    owner = _membership(1, role=Role.OWNER)
    admin = _membership(2, role=Role.ADMIN)

    MembershipAdministrationPolicy.ensure_target_manageable(
        actor_membership=owner,
        target_membership=admin,
        mutation=MembershipAdministrationMutation.UPDATE,
    )
    MembershipAdministrationPolicy.ensure_role_assignment_allowed(
        actor_membership=owner,
        target_membership=admin,
        new_role=Role.OWNER,
        memberships=[owner, admin],
    )


def test_owner_operations_respect_last_active_owner_policy() -> None:
    owner = _membership(1, role=Role.OWNER)

    with pytest.raises(LastActiveOwnerViolation):
        MembershipAdministrationPolicy.ensure_target_manageable(
            actor_membership=owner,
            target_membership=owner,
            mutation=MembershipAdministrationMutation.REMOVE,
            memberships=[owner],
        )

    with pytest.raises(LastActiveOwnerViolation):
        MembershipAdministrationPolicy.ensure_role_assignment_allowed(
            actor_membership=owner,
            target_membership=owner,
            new_role=Role.ADMIN,
            memberships=[owner],
        )


def test_admin_manages_non_owner_but_cannot_manage_or_create_owners() -> None:
    admin = _membership(1, role=Role.ADMIN)
    operator = _membership(2, role=Role.OPERATOR)
    owner = _membership(3, role=Role.OWNER)

    MembershipAdministrationPolicy.ensure_target_manageable(
        actor_membership=admin,
        target_membership=operator,
        mutation=MembershipAdministrationMutation.UPDATE,
    )
    MembershipAdministrationPolicy.ensure_role_assignment_allowed(
        actor_membership=admin,
        target_membership=operator,
        new_role=Role.REVIEWER,
    )

    with pytest.raises(MembershipAdministrationDenied, match="assign owner"):
        MembershipAdministrationPolicy.ensure_role_assignment_allowed(
            actor_membership=admin,
            target_membership=operator,
            new_role=Role.OWNER,
        )

    with pytest.raises(MembershipAdministrationDenied, match="manage owner"):
        MembershipAdministrationPolicy.ensure_target_manageable(
            actor_membership=admin,
            target_membership=owner,
            mutation=MembershipAdministrationMutation.UPDATE,
        )

    with pytest.raises(MembershipAdministrationDenied, match="manage owner"):
        MembershipAdministrationPolicy.ensure_target_manageable(
            actor_membership=admin,
            target_membership=owner,
            mutation=MembershipAdministrationMutation.SUSPEND,
        )

    with pytest.raises(MembershipAdministrationDenied, match="manage owner"):
        MembershipAdministrationPolicy.ensure_target_manageable(
            actor_membership=admin,
            target_membership=owner,
            mutation=MembershipAdministrationMutation.REMOVE,
        )

    with pytest.raises(MembershipAdministrationDenied, match="update owner"):
        MembershipAdministrationPolicy.ensure_role_assignment_allowed(
            actor_membership=admin,
            target_membership=owner,
            new_role=Role.ADMIN,
        )


def test_self_role_change_rule_prevents_non_owner_self_mutation() -> None:
    admin = _membership(1, role=Role.ADMIN)
    operator = _membership(2, role=Role.OPERATOR)
    owner = _membership(3, role=Role.OWNER)

    ensure_self_role_change_allowed(
        actor_membership=admin,
        target_membership=admin,
        new_role=Role.ADMIN,
    )

    with pytest.raises(MembershipAdministrationDenied, match="own role"):
        ensure_self_role_change_allowed(
            actor_membership=admin,
            target_membership=admin,
            new_role=Role.OWNER,
        )

    with pytest.raises(MembershipAdministrationDenied, match="own role"):
        ensure_self_role_change_allowed(
            actor_membership=operator,
            target_membership=operator,
            new_role=Role.ADMIN,
        )

    ensure_self_role_change_allowed(
        actor_membership=owner,
        target_membership=owner,
        new_role=Role.ADMIN,
    )


def test_tenant_boundary_rejects_mismatched_organizations() -> None:
    context = _context(role=Role.ADMIN)
    actor = _membership(1, role=Role.ADMIN)
    target = _membership(2, role=Role.OPERATOR, organization_id=OTHER_ORG_ID)

    with pytest.raises(TenantBoundaryViolation, match="target membership"):
        MembershipAdministrationPolicy.ensure_context_matches_target(
            context=context,
            target_membership=target,
        )

    with pytest.raises(TenantBoundaryViolation, match="Actor membership"):
        MembershipAdministrationPolicy.ensure_same_organization(
            actor_membership=actor,
            target_membership=target,
        )

    same_org_target = _membership(3, role=Role.OPERATOR)
    MembershipAdministrationPolicy.ensure_context_matches_target(
        context=context,
        target_membership=same_org_target,
    )
    MembershipAdministrationPolicy.ensure_same_organization(
        actor_membership=actor,
        target_membership=same_org_target,
    )


def _context(*, role: Role = Role.ADMIN) -> TenantContext:
    return TenantContext.create(
        user_id=_user_id(1),
        organization_id=ORG_ID,
        membership_id=_membership_id(1),
        role=role,
    )


def _membership(
    index: int,
    *,
    role: Role,
    organization_id: UUID = ORG_ID,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    membership = Membership.activate_directly(
        id=_membership_id(index),
        user_id=_user_id(index),
        organization_id=organization_id,
        role=role,
        now=NOW,
    )
    if status is MembershipStatus.ACTIVE:
        return membership
    if status is MembershipStatus.INVITED:
        return Membership.invite(
            id=membership.id,
            user_id=membership.user_id,
            organization_id=membership.organization_id,
            role=membership.role,
            now=NOW,
        )
    if status is MembershipStatus.SUSPENDED:
        return membership.suspend(now=NOW)
    if status is MembershipStatus.REMOVED:
        return membership.remove(now=NOW)
    raise AssertionError(status)


def _organization(*, organization_id: UUID = ORG_ID) -> Organization:
    return Organization.create(
        id=organization_id,
        name="WorkflowForge",
        slug=OrganizationSlug(f"org-{organization_id.hex[:8]}"),
        now=NOW,
    )


def _membership_id(index: int) -> UUID:
    return UUID(f"33333333-3333-4333-8333-{index:012d}")


def _user_id(index: int) -> UUID:
    return UUID(f"11111111-1111-4111-8111-{index:012d}")


def _organization_repository(
    organizations: dict[UUID, Organization],
) -> OrganizationRepository:
    return cast(OrganizationRepository, _OrganizationRepository(organizations))


def _membership_repository(
    memberships: dict[tuple[UUID, UUID], Membership],
) -> MembershipRepository:
    return cast(MembershipRepository, _MembershipRepository(memberships))


class _OrganizationRepository:
    def __init__(self, organizations: dict[UUID, Organization]) -> None:
        self._organizations = organizations

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self._organizations.get(organization_id)

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Unexpected organization repository call: {name}")


class _MembershipRepository:
    def __init__(self, memberships: dict[tuple[UUID, UUID], Membership]) -> None:
        self._memberships = memberships

    async def get_by_user_and_organization(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> Membership | None:
        return self._memberships.get((user_id, organization_id))

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Unexpected membership repository call: {name}")

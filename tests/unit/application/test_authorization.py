"""Authorization application policy tests."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_application.authorization import (
    AuthorizationPolicy,
    MembershipAdministrationDenied,
    MembershipAdministrationMutation,
    MembershipAdministrationPolicy,
    PermissionDenied,
    TenantBoundaryViolation,
    TenantContext,
    ensure_self_role_change_allowed,
)
from workflowforge_domain.identity import (
    InvalidIdentifier,
    LastActiveOwnerViolation,
    Membership,
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
) -> Membership:
    return Membership.activate_directly(
        id=_membership_id(index),
        user_id=_user_id(index),
        organization_id=organization_id,
        role=role,
        now=NOW,
    )


def _membership_id(index: int) -> UUID:
    return UUID(f"33333333-3333-4333-8333-{index:012d}")


def _user_id(index: int) -> UUID:
    return UUID(f"11111111-1111-4111-8111-{index:012d}")

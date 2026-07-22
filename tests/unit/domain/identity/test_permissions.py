"""Permission and role mapping tests."""

import pytest
from workflowforge_domain.identity import (
    IdentityDomainError,
    Permission,
    Role,
    permissions_for_role,
)


def test_permission_values_are_stable_and_complete() -> None:
    assert [permission.value for permission in Permission] == [
        "organization.read",
        "organization.update",
        "membership.read",
        "membership.invite",
        "membership.update",
        "membership.remove",
        "audit.read",
        "security.manage",
        "api_keys.manage",
        "provider_credentials.manage",
    ]
    assert str(Permission.ORGANIZATION_READ) == "organization.read"


def test_every_role_has_explicit_permissions() -> None:
    assert {role: permissions_for_role(role) for role in Role} == {
        Role.OWNER: frozenset(Permission),
        Role.ADMIN: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.ORGANIZATION_UPDATE,
                Permission.MEMBERSHIP_READ,
                Permission.MEMBERSHIP_INVITE,
                Permission.MEMBERSHIP_UPDATE,
                Permission.MEMBERSHIP_REMOVE,
                Permission.AUDIT_READ,
                Permission.API_KEYS_MANAGE,
                Permission.PROVIDER_CREDENTIALS_MANAGE,
            }
        ),
        Role.OPERATOR: frozenset({Permission.ORGANIZATION_READ}),
        Role.REVIEWER: frozenset({Permission.ORGANIZATION_READ}),
        Role.AUDITOR: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.MEMBERSHIP_READ,
                Permission.AUDIT_READ,
            }
        ),
    }


def test_owner_gets_all_permissions() -> None:
    assert permissions_for_role(Role.OWNER) == frozenset(Permission)


def test_admin_permission_matrix_is_exact_and_excludes_security_manage() -> None:
    permissions = permissions_for_role(Role.ADMIN)

    assert permissions == frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.ORGANIZATION_UPDATE,
            Permission.MEMBERSHIP_READ,
            Permission.MEMBERSHIP_INVITE,
            Permission.MEMBERSHIP_UPDATE,
            Permission.MEMBERSHIP_REMOVE,
            Permission.AUDIT_READ,
            Permission.API_KEYS_MANAGE,
            Permission.PROVIDER_CREDENTIALS_MANAGE,
        }
    )
    assert Permission.SECURITY_MANAGE not in permissions


def test_operator_reviewer_and_auditor_permission_matrices_are_exact() -> None:
    assert permissions_for_role(Role.OPERATOR) == frozenset({Permission.ORGANIZATION_READ})
    assert permissions_for_role(Role.REVIEWER) == frozenset({Permission.ORGANIZATION_READ})
    assert permissions_for_role(Role.AUDITOR) == frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.MEMBERSHIP_READ,
            Permission.AUDIT_READ,
        }
    )


def test_permission_results_are_immutable_and_not_shared_mutably() -> None:
    permissions = permissions_for_role(Role.ADMIN)

    assert isinstance(permissions, frozenset)
    assert permissions_for_role(Role.ADMIN) == permissions
    assert permissions_for_role(Role.ADMIN) is permissions

    with pytest.raises(AttributeError):
        permissions.add(Permission.SECURITY_MANAGE)  # type: ignore[attr-defined]


def test_invalid_role_fails_safely() -> None:
    with pytest.raises(IdentityDomainError, match="valid Role"):
        permissions_for_role("owner")  # type: ignore[arg-type]

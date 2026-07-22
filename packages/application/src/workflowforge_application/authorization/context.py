"""Tenant authorization context."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from workflowforge_domain.identity import Permission, Role, permissions_for_role
from workflowforge_domain.identity.entities import validate_uuid


@dataclass(frozen=True, slots=True, init=False)
class TenantContext:
    """Immutable tenant context resolved by trusted application composition."""

    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    role: Role
    permissions: frozenset[Permission]

    def __init__(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        role: Role,
    ) -> None:
        self._set_validated(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role=role,
            permissions=permissions_for_role(role),
        )

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        role: Role,
    ) -> TenantContext:
        """Create context by resolving permissions from the role."""

        return cls(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role=role,
        )

    @classmethod
    def trusted_with_permissions(
        cls,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        role: Role,
        permissions: Iterable[Permission],
    ) -> TenantContext:
        """Create context with explicit trusted permissions for tests and adapters."""

        context = object.__new__(cls)
        context._set_validated(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role=role,
            permissions=frozenset(permissions),
        )
        return context

    def _set_validated(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        role: Role,
        permissions: frozenset[Permission],
    ) -> None:
        validate_uuid(user_id, field_name="Tenant context user identifier")
        validate_uuid(
            organization_id,
            field_name="Tenant context organization identifier",
        )
        validate_uuid(
            membership_id,
            field_name="Tenant context membership identifier",
        )
        if not isinstance(role, Role):
            msg = "Tenant context role must be a Role."
            raise TypeError(msg)
        if not isinstance(permissions, frozenset):
            msg = "Tenant context permissions must be a frozenset."
            raise TypeError(msg)
        if any(not isinstance(permission, Permission) for permission in permissions):
            msg = "Tenant context permissions must contain Permission values."
            raise TypeError(msg)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "organization_id", organization_id)
        object.__setattr__(self, "membership_id", membership_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "permissions", permissions)

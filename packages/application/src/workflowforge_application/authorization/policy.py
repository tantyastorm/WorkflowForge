"""Authorization policies."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from workflowforge_domain.identity import (
    LastActiveOwnerViolation,
    Membership,
    MembershipMutation,
    MembershipPolicy,
    MembershipStatus,
    Permission,
    Role,
)

from workflowforge_application.authorization.context import TenantContext
from workflowforge_application.authorization.errors import (
    MembershipAdministrationDenied,
    PermissionDenied,
    TenantBoundaryViolation,
)


class MembershipAdministrationMutation(StrEnum):
    """Membership administration operations with target restrictions."""

    UPDATE = "update"
    SUSPEND = "suspend"
    REMOVE = "remove"
    CHANGE_ROLE = "change_role"
    INVITE = "invite"


class AuthorizationPolicy:
    """Centralized side-effect-free authorization policy."""

    def allows(self, context: TenantContext, permission: Permission) -> bool:
        """Return whether the context has a permission."""

        return permission in context.permissions

    def allows_any(
        self,
        context: TenantContext,
        permissions: Iterable[Permission],
    ) -> bool:
        """Return whether the context has any permission from a set."""

        return any(permission in context.permissions for permission in permissions)

    def allows_all(
        self,
        context: TenantContext,
        permissions: Iterable[Permission],
    ) -> bool:
        """Return whether the context has every permission from a set."""

        return all(permission in context.permissions for permission in permissions)

    def require(self, context: TenantContext, permission: Permission) -> None:
        """Require a permission or raise a transport-neutral denial."""

        if not self.allows(context, permission):
            raise PermissionDenied(
                user_id=context.user_id,
                organization_id=context.organization_id,
                permission=permission,
            )

    def require_any(
        self,
        context: TenantContext,
        permissions: Iterable[Permission],
    ) -> None:
        """Require at least one permission or raise a transport-neutral denial."""

        permission_set = frozenset(permissions)
        if not permission_set:
            msg = "At least one permission is required."
            raise ValueError(msg)
        if not self.allows_any(context, permission_set):
            raise PermissionDenied(
                user_id=context.user_id,
                organization_id=context.organization_id,
                permission=next(iter(permission_set)),
            )

    def require_all(
        self,
        context: TenantContext,
        permissions: Iterable[Permission],
    ) -> None:
        """Require every permission or raise a transport-neutral denial."""

        permission_set = frozenset(permissions)
        if not permission_set:
            msg = "At least one permission is required."
            raise ValueError(msg)
        missing = permission_set.difference(context.permissions)
        if missing:
            raise PermissionDenied(
                user_id=context.user_id,
                organization_id=context.organization_id,
                permission=next(iter(missing)),
            )


class MembershipAdministrationPolicy:
    """Pure membership administration target restrictions."""

    @staticmethod
    def ensure_context_matches_target(
        *,
        context: TenantContext,
        target_membership: Membership,
    ) -> None:
        """Ensure a target membership belongs to the tenant context."""

        if context.organization_id != target_membership.organization_id:
            raise TenantBoundaryViolation(
                message="Tenant context does not match target membership",
                organization_id=target_membership.organization_id,
                expected_organization_id=context.organization_id,
            )

    @staticmethod
    def ensure_same_organization(
        *,
        actor_membership: Membership,
        target_membership: Membership,
    ) -> None:
        """Ensure actor and target memberships belong to one organization."""

        if actor_membership.organization_id != target_membership.organization_id:
            raise TenantBoundaryViolation(
                message="Actor membership does not match target membership",
                organization_id=target_membership.organization_id,
                expected_organization_id=actor_membership.organization_id,
            )

    @staticmethod
    def ensure_target_manageable(
        *,
        actor_membership: Membership,
        target_membership: Membership,
        mutation: MembershipAdministrationMutation,
        memberships: Iterable[Membership] = (),
    ) -> None:
        """Ensure an actor may manage a target membership."""

        MembershipAdministrationPolicy.ensure_same_organization(
            actor_membership=actor_membership,
            target_membership=target_membership,
        )

        if actor_membership.role is Role.OWNER:
            _ensure_owner_last_owner_rule(
                target_membership=target_membership,
                mutation=mutation,
                memberships=memberships,
            )
            return

        if actor_membership.role is Role.ADMIN:
            if target_membership.role is Role.OWNER:
                _raise_membership_administration_denied(
                    actor_membership=actor_membership,
                    target_membership=target_membership,
                    reason="admins cannot manage owner memberships",
                )
            return

        _raise_membership_administration_denied(
            actor_membership=actor_membership,
            target_membership=target_membership,
            reason="membership target policy requires owner or admin role",
        )

    @staticmethod
    def ensure_role_assignment_allowed(
        *,
        actor_membership: Membership,
        target_membership: Membership,
        new_role: Role,
        memberships: Iterable[Membership] = (),
    ) -> None:
        """Ensure an actor may assign a target membership role."""

        MembershipAdministrationPolicy.ensure_same_organization(
            actor_membership=actor_membership,
            target_membership=target_membership,
        )
        ensure_self_role_change_allowed(
            actor_membership=actor_membership,
            target_membership=target_membership,
            new_role=new_role,
        )

        if target_membership.role is new_role:
            return

        if actor_membership.role is Role.OWNER:
            if target_membership.role is Role.OWNER and new_role is not Role.OWNER:
                MembershipPolicy.ensure_not_last_active_owner(
                    target=target_membership,
                    memberships=memberships,
                    mutation=MembershipMutation.DEMOTE_OWNER,
                )
            return

        if actor_membership.role is Role.ADMIN:
            if new_role is Role.OWNER:
                _raise_membership_administration_denied(
                    actor_membership=actor_membership,
                    target_membership=target_membership,
                    reason="admins cannot assign owner role",
                )
            if target_membership.role is Role.OWNER:
                _raise_membership_administration_denied(
                    actor_membership=actor_membership,
                    target_membership=target_membership,
                    reason="admins cannot update owner memberships",
                )
            return

        _raise_membership_administration_denied(
            actor_membership=actor_membership,
            target_membership=target_membership,
            reason="role assignment requires owner or admin role",
        )


def ensure_self_role_change_allowed(
    *,
    actor_membership: Membership,
    target_membership: Membership,
    new_role: Role,
) -> None:
    """Prevent non-owner self-promotion or self-role mutation."""

    if actor_membership.id != target_membership.id:
        return
    if new_role is target_membership.role:
        return
    if actor_membership.role is Role.OWNER:
        return

    _raise_membership_administration_denied(
        actor_membership=actor_membership,
        target_membership=target_membership,
        reason="non-owner memberships cannot change their own role",
    )


def _ensure_owner_last_owner_rule(
    *,
    target_membership: Membership,
    mutation: MembershipAdministrationMutation,
    memberships: Iterable[Membership],
) -> None:
    if target_membership.role is not Role.OWNER:
        return
    if target_membership.status is not MembershipStatus.ACTIVE:
        return

    domain_mutation: MembershipMutation | None = None
    if mutation is MembershipAdministrationMutation.SUSPEND:
        domain_mutation = MembershipMutation.SUSPEND_OWNER
    elif mutation is MembershipAdministrationMutation.REMOVE:
        domain_mutation = MembershipMutation.REMOVE_OWNER
    elif mutation is MembershipAdministrationMutation.CHANGE_ROLE:
        domain_mutation = MembershipMutation.DEMOTE_OWNER

    if domain_mutation is not None:
        try:
            MembershipPolicy.ensure_not_last_active_owner(
                target=target_membership,
                memberships=memberships,
                mutation=domain_mutation,
            )
        except LastActiveOwnerViolation:
            raise


def _raise_membership_administration_denied(
    *,
    actor_membership: Membership,
    target_membership: Membership,
    reason: str,
) -> None:
    raise MembershipAdministrationDenied(
        actor_membership_id=actor_membership.id,
        target_membership_id=target_membership.id,
        organization_id=actor_membership.organization_id,
        reason=reason,
    )

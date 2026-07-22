"""Authorization errors."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from workflowforge_domain.identity import MembershipStatus, Permission

from workflowforge_application.errors import ApplicationError


class AuthorizationError(ApplicationError):
    """Base class for transport-neutral authorization failures."""


@dataclass(frozen=True, slots=True)
class TenantAccessDenied(AuthorizationError):
    """Raised when a user cannot enter a selected tenant context."""

    user_id: UUID
    organization_id: UUID
    reason: str

    def __str__(self) -> str:
        return (
            f"Tenant access denied for user {self.user_id} "
            f"in organization {self.organization_id}: {self.reason}."
        )


@dataclass(frozen=True, slots=True)
class TenantMembershipInactive(AuthorizationError):
    """Raised when tenant membership exists but cannot authorize access."""

    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    status: MembershipStatus

    def __str__(self) -> str:
        return (
            f"Tenant membership {self.membership_id} for user {self.user_id} "
            f"in organization {self.organization_id} is {self.status.value}."
        )


@dataclass(frozen=True, slots=True)
class PermissionDenied(AuthorizationError):
    """Raised when a tenant context lacks a requested permission."""

    user_id: UUID
    organization_id: UUID
    permission: Permission

    def __str__(self) -> str:
        return (
            "Permission denied for user "
            f"{self.user_id} in organization {self.organization_id}: "
            f"{self.permission.value}."
        )


@dataclass(frozen=True, slots=True)
class TenantBoundaryViolation(AuthorizationError):
    """Raised when supplied tenant identities do not match."""

    message: str
    organization_id: UUID
    expected_organization_id: UUID

    def __str__(self) -> str:
        return (
            f"{self.message}: organization {self.organization_id} does not match "
            f"expected organization {self.expected_organization_id}."
        )


@dataclass(frozen=True, slots=True)
class MembershipAdministrationDenied(AuthorizationError):
    """Raised when membership target rules reject an operation."""

    actor_membership_id: UUID
    target_membership_id: UUID
    organization_id: UUID
    reason: str

    def __str__(self) -> str:
        return (
            "Membership administration denied for actor membership "
            f"{self.actor_membership_id} targeting {self.target_membership_id} "
            f"in organization {self.organization_id}: {self.reason}."
        )

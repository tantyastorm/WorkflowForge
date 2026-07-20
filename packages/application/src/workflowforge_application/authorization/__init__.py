"""Public authorization application API."""

from workflowforge_application.authorization.context import TenantContext
from workflowforge_application.authorization.errors import (
    AuthorizationError,
    MembershipAdministrationDenied,
    PermissionDenied,
    TenantBoundaryViolation,
)
from workflowforge_application.authorization.policy import (
    AuthorizationPolicy,
    MembershipAdministrationMutation,
    MembershipAdministrationPolicy,
    ensure_self_role_change_allowed,
)

__all__ = [
    "AuthorizationError",
    "AuthorizationPolicy",
    "MembershipAdministrationDenied",
    "MembershipAdministrationMutation",
    "MembershipAdministrationPolicy",
    "PermissionDenied",
    "TenantBoundaryViolation",
    "TenantContext",
    "ensure_self_role_change_allowed",
]

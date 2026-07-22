"""Public authorization application API."""

from workflowforge_application.authorization.context import TenantContext
from workflowforge_application.authorization.errors import (
    AuthorizationError,
    MembershipAdministrationDenied,
    PermissionDenied,
    TenantAccessDenied,
    TenantBoundaryViolation,
    TenantMembershipInactive,
)
from workflowforge_application.authorization.policy import (
    AuthorizationPolicy,
    MembershipAdministrationMutation,
    MembershipAdministrationPolicy,
    ensure_self_role_change_allowed,
)
from workflowforge_application.authorization.tenant_resolution import (
    ResolveTenantContext,
    ResolveTenantContextCommand,
)

__all__ = [
    "AuthorizationError",
    "AuthorizationPolicy",
    "MembershipAdministrationDenied",
    "MembershipAdministrationMutation",
    "MembershipAdministrationPolicy",
    "PermissionDenied",
    "ResolveTenantContext",
    "ResolveTenantContextCommand",
    "TenantAccessDenied",
    "TenantBoundaryViolation",
    "TenantContext",
    "TenantMembershipInactive",
    "ensure_self_role_change_allowed",
]

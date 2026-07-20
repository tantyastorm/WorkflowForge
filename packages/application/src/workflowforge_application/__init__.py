"""WorkflowForge application-layer package."""

from workflowforge_application.authorization import (
    AuthorizationError,
    AuthorizationPolicy,
    MembershipAdministrationDenied,
    MembershipAdministrationMutation,
    MembershipAdministrationPolicy,
    PermissionDenied,
    TenantBoundaryViolation,
    TenantContext,
    ensure_self_role_change_allowed,
)
from workflowforge_application.errors import ApplicationError
from workflowforge_application.identity import (
    DuplicateNormalizedEmailError,
    DuplicateOrganizationMembershipError,
    DuplicateOrganizationSlugError,
    IdentityApplicationError,
    MembershipRepository,
    MissingIdentityReferenceError,
    OrganizationRepository,
    UserRepository,
)

__all__ = [
    "ApplicationError",
    "AuthorizationError",
    "AuthorizationPolicy",
    "DuplicateNormalizedEmailError",
    "DuplicateOrganizationMembershipError",
    "DuplicateOrganizationSlugError",
    "IdentityApplicationError",
    "MembershipAdministrationDenied",
    "MembershipAdministrationMutation",
    "MembershipAdministrationPolicy",
    "MembershipRepository",
    "MissingIdentityReferenceError",
    "OrganizationRepository",
    "PermissionDenied",
    "TenantBoundaryViolation",
    "TenantContext",
    "UserRepository",
    "__version__",
    "ensure_self_role_change_allowed",
]

__version__ = "0.1.0a1"

"""Identity application errors."""

from workflowforge_application.errors import ApplicationError


class IdentityApplicationError(ApplicationError):
    """Base class for identity application failures."""


class DuplicateNormalizedEmailError(IdentityApplicationError):
    """Raised when a normalized email already exists."""


class DuplicateOrganizationSlugError(IdentityApplicationError):
    """Raised when an organization slug already exists."""


class DuplicateOrganizationMembershipError(IdentityApplicationError):
    """Raised when a user already has membership in an organization."""


class MissingIdentityReferenceError(IdentityApplicationError):
    """Raised when a referenced user or organization is missing."""

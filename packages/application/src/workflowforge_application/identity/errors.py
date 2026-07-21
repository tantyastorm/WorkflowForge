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


class InvalidCredentialsError(IdentityApplicationError):
    """Raised when email/password authentication fails generically."""


class UserAuthenticationDisabledError(IdentityApplicationError):
    """Raised when a disabled user provides otherwise valid credentials."""


class InvalidPasswordError(IdentityApplicationError):
    """Raised when a plaintext password violates application password policy."""


class DuplicatePasswordCredentialError(IdentityApplicationError):
    """Raised when a password credential conflicts with an existing credential."""


class MalformedStoredCredentialError(IdentityApplicationError):
    """Raised when durable credential state cannot be safely interpreted."""

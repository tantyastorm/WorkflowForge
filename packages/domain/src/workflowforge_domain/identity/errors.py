"""Identity and tenancy domain errors."""

from workflowforge_domain.errors import DomainError


class IdentityDomainError(DomainError):
    """Base class for identity and tenancy domain rule violations."""


class InvalidEmailAddress(IdentityDomainError):
    """Raised when an email address value is invalid."""


class InvalidOrganizationSlug(IdentityDomainError):
    """Raised when an organization slug value is invalid."""


class InvalidDisplayName(IdentityDomainError):
    """Raised when a user display name is invalid."""


class InvalidOrganizationName(IdentityDomainError):
    """Raised when an organization name is invalid."""


class InvalidTimestamp(IdentityDomainError):
    """Raised when a domain timestamp is invalid."""


class InvalidIdentifier(IdentityDomainError):
    """Raised when an identity or tenancy identifier is invalid."""


class InvalidMembershipTransition(IdentityDomainError):
    """Raised when a membership lifecycle transition is not allowed."""


class MembershipAlreadyRemoved(InvalidMembershipTransition):
    """Raised when a removed membership receives a forbidden mutation."""


class LastActiveOwnerViolation(IdentityDomainError):
    """Raised when a mutation would remove the final active owner."""

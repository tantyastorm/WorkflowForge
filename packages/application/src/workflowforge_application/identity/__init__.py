"""Identity application ports and errors."""

from workflowforge_application.identity.authentication import (
    AuthenticatedUser,
    AuthenticateUser,
    AuthenticateUserCommand,
    SetUserPassword,
    SetUserPasswordCommand,
)
from workflowforge_application.identity.credentials import PasswordCredential
from workflowforge_application.identity.errors import (
    DuplicateNormalizedEmailError,
    DuplicateOrganizationMembershipError,
    DuplicateOrganizationSlugError,
    DuplicatePasswordCredentialError,
    IdentityApplicationError,
    InvalidCredentialsError,
    InvalidPasswordError,
    MalformedStoredCredentialError,
    MissingIdentityReferenceError,
    UserAuthenticationDisabledError,
)
from workflowforge_application.identity.ports import (
    MembershipRepository,
    OrganizationRepository,
    PasswordCredentialRepository,
    PasswordHasher,
    UserRepository,
)

__all__ = [
    "AuthenticateUser",
    "AuthenticateUserCommand",
    "AuthenticatedUser",
    "DuplicatePasswordCredentialError",
    "DuplicateNormalizedEmailError",
    "DuplicateOrganizationMembershipError",
    "DuplicateOrganizationSlugError",
    "IdentityApplicationError",
    "InvalidCredentialsError",
    "InvalidPasswordError",
    "MalformedStoredCredentialError",
    "MembershipRepository",
    "MissingIdentityReferenceError",
    "OrganizationRepository",
    "PasswordCredential",
    "PasswordCredentialRepository",
    "PasswordHasher",
    "SetUserPassword",
    "SetUserPasswordCommand",
    "UserAuthenticationDisabledError",
    "UserRepository",
]

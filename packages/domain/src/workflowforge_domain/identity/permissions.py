"""Code-defined role-to-permission mapping."""

from types import MappingProxyType

from workflowforge_domain.identity.enums import Permission, Role
from workflowforge_domain.identity.errors import IdentityDomainError

_ROLE_PERMISSIONS = MappingProxyType(
    {
        Role.OWNER: frozenset(Permission),
        Role.ADMIN: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.ORGANIZATION_UPDATE,
                Permission.MEMBERSHIP_READ,
                Permission.MEMBERSHIP_INVITE,
                Permission.MEMBERSHIP_UPDATE,
                Permission.MEMBERSHIP_REMOVE,
                Permission.AUDIT_READ,
                Permission.API_KEYS_MANAGE,
                Permission.PROVIDER_CREDENTIALS_MANAGE,
                Permission.DOCUMENT_READ,
                Permission.DOCUMENT_WRITE,
                Permission.DOCUMENT_ARCHIVE,
                Permission.DOCUMENT_DOWNLOAD,
                Permission.DOCUMENT_VERSION_READ,
                Permission.DOCUMENT_VERSION_CREATE,
                Permission.ARTIFACT_READ,
                Permission.ARTIFACT_DOWNLOAD,
            }
        ),
        Role.OPERATOR: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.DOCUMENT_READ,
                Permission.DOCUMENT_WRITE,
                Permission.DOCUMENT_DOWNLOAD,
                Permission.DOCUMENT_VERSION_READ,
                Permission.DOCUMENT_VERSION_CREATE,
                Permission.ARTIFACT_READ,
                Permission.ARTIFACT_DOWNLOAD,
            }
        ),
        Role.REVIEWER: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.DOCUMENT_READ,
                Permission.DOCUMENT_DOWNLOAD,
                Permission.DOCUMENT_VERSION_READ,
                Permission.ARTIFACT_READ,
                Permission.ARTIFACT_DOWNLOAD,
            }
        ),
        Role.AUDITOR: frozenset(
            {
                Permission.ORGANIZATION_READ,
                Permission.MEMBERSHIP_READ,
                Permission.AUDIT_READ,
                Permission.DOCUMENT_READ,
                Permission.DOCUMENT_DOWNLOAD,
                Permission.DOCUMENT_VERSION_READ,
                Permission.ARTIFACT_READ,
                Permission.ARTIFACT_DOWNLOAD,
            }
        ),
    }
)


def permissions_for_role(role: Role) -> frozenset[Permission]:
    """Return immutable permissions for a role."""

    if not isinstance(role, Role):
        msg = "Role must be a valid Role value."
        raise IdentityDomainError(msg)
    try:
        return _ROLE_PERMISSIONS[role]
    except KeyError as exc:
        msg = f"No permissions are defined for role {role.value!r}."
        raise IdentityDomainError(msg) from exc

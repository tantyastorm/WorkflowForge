"""Identity and tenancy enums."""

from enum import StrEnum


class Role(StrEnum):
    """Organization membership role."""

    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"


class MembershipStatus(StrEnum):
    """Organization membership lifecycle status."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class Permission(StrEnum):
    """Stable organization permission name."""

    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_UPDATE = "organization.update"
    MEMBERSHIP_READ = "membership.read"
    MEMBERSHIP_INVITE = "membership.invite"
    MEMBERSHIP_UPDATE = "membership.update"
    MEMBERSHIP_REMOVE = "membership.remove"
    AUDIT_READ = "audit.read"
    SECURITY_MANAGE = "security.manage"
    API_KEYS_MANAGE = "api_keys.manage"
    PROVIDER_CREDENTIALS_MANAGE = "provider_credentials.manage"

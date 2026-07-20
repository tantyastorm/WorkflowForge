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

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
    DOCUMENT_READ = "document.read"
    DOCUMENT_WRITE = "document.write"
    DOCUMENT_ARCHIVE = "document.archive"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_VERSION_READ = "document_version.read"
    DOCUMENT_VERSION_CREATE = "document_version.create"
    ARTIFACT_READ = "artifact.read"
    ARTIFACT_DOWNLOAD = "artifact.download"
    BATCH_READ = "batch.read"
    BATCH_WRITE = "batch.write"
    BATCH_ARCHIVE = "batch.archive"
    BATCH_MANAGE_DOCUMENTS = "batch.manage_documents"
    CASE_READ = "case.read"
    CASE_WRITE = "case.write"
    CASE_ARCHIVE = "case.archive"
    CASE_MANAGE_DOCUMENTS = "case.manage_documents"
    CASE_COMMENT = "case.comment"
    CASE_TASK = "case.task"
    CASE_DECISION = "case.decision"

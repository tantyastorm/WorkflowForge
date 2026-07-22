"""Audit application errors."""

from workflowforge_application.errors import ApplicationError


class AuditApplicationError(ApplicationError):
    """Base class for audit application failures."""


class AuditPersistenceError(AuditApplicationError):
    """Raised when durable audit persistence fails."""

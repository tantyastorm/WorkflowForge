"""Document application errors."""

from workflowforge_application.errors import ApplicationError


class DocumentApplicationError(ApplicationError):
    """Base class for document application failures."""


class DocumentNotFoundError(DocumentApplicationError):
    """Raised when a document cannot be found."""


class DuplicateDocumentContentError(DocumentApplicationError):
    """Raised when the repository detects duplicate document content."""


class InvalidDocumentLifecycleOperationError(DocumentApplicationError):
    """Raised when a requested lifecycle operation is invalid."""

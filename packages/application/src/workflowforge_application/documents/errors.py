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


class ConcurrencyConflictError(DocumentApplicationError):
    """Raised when optimistic concurrency state is stale."""


class UploadValidationError(DocumentApplicationError):
    """Raised when uploaded bytes or metadata fail validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UploadIdempotencyError(DocumentApplicationError):
    """Base class for upload idempotency failures."""

    code = "idempotency_error"


class InvalidIdempotencyKeyError(UploadIdempotencyError):
    """Raised when an idempotency key is invalid."""

    code = "invalid_idempotency_key"


class IdempotencyConflictError(UploadIdempotencyError):
    """Raised when a key is reused for a different request."""

    code = "idempotency_conflict"


class IdempotencyInProgressError(UploadIdempotencyError):
    """Raised when another request is processing the same key."""

    code = "idempotency_in_progress"


class ObjectStorageUnavailableError(DocumentApplicationError):
    """Raised when object storage cannot complete upload work."""

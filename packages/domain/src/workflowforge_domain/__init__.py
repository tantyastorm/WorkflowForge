"""Framework-independent WorkflowForge domain package."""

from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentError,
    DocumentId,
    DocumentStatus,
    InvalidDocumentTransitionError,
    StorageObjectKey,
)
from workflowforge_domain.errors import DomainError

__all__ = [
    "ContentHash",
    "Document",
    "DocumentError",
    "DocumentId",
    "DocumentStatus",
    "DomainError",
    "InvalidDocumentTransitionError",
    "StorageObjectKey",
    "__version__",
]

__version__ = "0.1.0a1"

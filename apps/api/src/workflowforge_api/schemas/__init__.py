"""API response schemas."""

from workflowforge_api.schemas.errors import ErrorDetail, ErrorResponse
from workflowforge_api.schemas.health import (
    DependencyHealthResponse,
    DependencyHealthResponseItem,
    LiveHealthResponse,
    ReadyHealthResponse,
)

__all__ = [
    "DependencyHealthResponse",
    "DependencyHealthResponseItem",
    "ErrorDetail",
    "ErrorResponse",
    "LiveHealthResponse",
    "ReadyHealthResponse",
]

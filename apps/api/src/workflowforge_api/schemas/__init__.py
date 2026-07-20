"""API response schemas."""

from workflowforge_api.schemas.errors import ErrorDetail, ErrorResponse
from workflowforge_api.schemas.health import LiveHealthResponse, ReadyHealthResponse

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "LiveHealthResponse",
    "ReadyHealthResponse",
]

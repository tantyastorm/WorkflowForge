"""HTTP error response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Stable API error detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    correlation_id: str | None = None


class ErrorResponse(BaseModel):
    """Stable API error envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error: ErrorDetail

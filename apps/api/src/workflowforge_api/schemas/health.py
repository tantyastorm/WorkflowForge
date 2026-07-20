"""HTTP health response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LiveHealthResponse(BaseModel):
    """Liveness response for the API process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    service: Literal["api"]


class ReadyHealthResponse(BaseModel):
    """Readiness response for the API process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ready", "not_ready"]
    service: Literal["api"]


class DependencyHealthResponseItem(BaseModel):
    """HTTP dependency health response item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["healthy", "unhealthy"]
    latency_ms: float
    detail: str | None = None


class DependencyHealthResponse(BaseModel):
    """HTTP dependency health response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["healthy", "unhealthy"]
    checked_at: datetime
    dependencies: dict[str, DependencyHealthResponseItem]

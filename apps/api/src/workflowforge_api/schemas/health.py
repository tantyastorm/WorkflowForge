"""HTTP health response schemas."""

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

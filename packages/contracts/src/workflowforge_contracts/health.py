"""Transport-neutral health contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HealthState(StrEnum):
    """Overall system health state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyState(StrEnum):
    """Health state for one dependency."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DependencyHealth(BaseModel):
    """Transport-neutral health result for one dependency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    state: DependencyState
    detail: str | None = None


class SystemHealth(BaseModel):
    """Transport-neutral system health result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: HealthState
    service: str = Field(min_length=1)
    dependencies: tuple[DependencyHealth, ...] = ()

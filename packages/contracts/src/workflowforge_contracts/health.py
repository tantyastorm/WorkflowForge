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


class DependencyStatus(StrEnum):
    """Required dependency status for runtime health aggregation."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class DependencyHealthResult(BaseModel):
    """Transport-neutral health result for one required dependency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    status: DependencyStatus
    latency_ms: float = Field(ge=0)
    detail: str | None = None


class DependencyHealthReport(BaseModel):
    """Transport-neutral aggregate dependency health report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DependencyStatus
    dependencies: tuple[DependencyHealthResult, ...] = ()


class SystemHealth(BaseModel):
    """Transport-neutral system health result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: HealthState
    service: str = Field(min_length=1)
    dependencies: tuple[DependencyHealth, ...] = ()

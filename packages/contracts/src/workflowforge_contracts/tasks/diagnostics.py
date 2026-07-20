"""Transport-neutral diagnostic task contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DIAGNOSTIC_ECHO_TASK_NAME = "system.diagnostics.echo"
SCHEDULER_HEARTBEAT_TASK_NAME = "system.diagnostics.scheduler_heartbeat"


class DiagnosticEchoPayload(BaseModel):
    """Safe diagnostic echo payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1, max_length=256)


class DiagnosticEchoResult(BaseModel):
    """Safe diagnostic echo result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str
    task_id: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    processed_at: datetime
    worker: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)


class SchedulerHeartbeatResult(BaseModel):
    """Scheduler heartbeat write result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    observed_at: datetime
    ttl_seconds: int = Field(gt=0)

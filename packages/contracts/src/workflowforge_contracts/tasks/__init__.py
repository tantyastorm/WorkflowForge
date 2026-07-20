"""Task payload and result contracts."""

from workflowforge_contracts.tasks.diagnostics import (
    DIAGNOSTIC_ECHO_TASK_NAME,
    SCHEDULER_HEARTBEAT_TASK_NAME,
    DiagnosticEchoPayload,
    DiagnosticEchoResult,
    SchedulerHeartbeatResult,
)

__all__ = [
    "DIAGNOSTIC_ECHO_TASK_NAME",
    "SCHEDULER_HEARTBEAT_TASK_NAME",
    "DiagnosticEchoPayload",
    "DiagnosticEchoResult",
    "SchedulerHeartbeatResult",
]

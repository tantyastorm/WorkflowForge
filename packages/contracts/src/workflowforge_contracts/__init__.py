"""Stable transport-neutral WorkflowForge contracts."""

from workflowforge_contracts.health import (
    DependencyHealth,
    DependencyHealthReport,
    DependencyHealthResult,
    DependencyState,
    DependencyStatus,
    HealthState,
    SystemHealth,
)
from workflowforge_contracts.tasks import (
    DIAGNOSTIC_ECHO_TASK_NAME,
    SCHEDULER_HEARTBEAT_TASK_NAME,
    DiagnosticEchoPayload,
    DiagnosticEchoResult,
    SchedulerHeartbeatResult,
)

__all__ = [
    "DIAGNOSTIC_ECHO_TASK_NAME",
    "DependencyHealth",
    "DependencyHealthReport",
    "DependencyHealthResult",
    "DependencyState",
    "DependencyStatus",
    "DiagnosticEchoPayload",
    "DiagnosticEchoResult",
    "HealthState",
    "SCHEDULER_HEARTBEAT_TASK_NAME",
    "SchedulerHeartbeatResult",
    "SystemHealth",
    "__version__",
]

__version__ = "0.1.0a1"

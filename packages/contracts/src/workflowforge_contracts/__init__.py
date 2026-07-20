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

__all__ = [
    "DependencyHealth",
    "DependencyHealthReport",
    "DependencyHealthResult",
    "DependencyState",
    "DependencyStatus",
    "HealthState",
    "SystemHealth",
    "__version__",
]

__version__ = "0.1.0a1"

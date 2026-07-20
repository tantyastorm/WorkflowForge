"""Stable transport-neutral WorkflowForge contracts."""

from workflowforge_contracts.health import (
    DependencyHealth,
    DependencyState,
    HealthState,
    SystemHealth,
)

__all__ = [
    "DependencyHealth",
    "DependencyState",
    "HealthState",
    "SystemHealth",
    "__version__",
]

__version__ = "0.1.0a1"

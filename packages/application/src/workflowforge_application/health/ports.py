"""Application ports for dependency health checks."""

from typing import Protocol

from workflowforge_contracts import DependencyHealthResult


class DependencyHealthCheck(Protocol):
    """Port implemented by infrastructure dependency health checks."""

    @property
    def name(self) -> str:
        """Stable dependency name."""

    async def check(self) -> DependencyHealthResult:
        """Check dependency health."""

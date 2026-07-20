"""Dependency health aggregation service."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from workflowforge_contracts import (
    DependencyHealthReport,
    DependencyHealthResult,
    DependencyStatus,
)

from workflowforge_application.health.ports import DependencyHealthCheck

DEFAULT_DEPENDENCY_TIMEOUT_SECONDS = 3.0
_SANITIZED_FAILURE_DETAIL = "Dependency check failed."
_SANITIZED_TIMEOUT_DETAIL = "Dependency check timed out."


class DependencyHealthService:
    """Run required dependency checks concurrently and aggregate their status."""

    def __init__(
        self,
        checks: Sequence[DependencyHealthCheck],
        *,
        timeout_seconds: float = DEFAULT_DEPENDENCY_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            msg = "Dependency health timeout must be positive."
            raise ValueError(msg)
        self._checks = tuple(checks)
        self._timeout_seconds = timeout_seconds

    async def check(self) -> DependencyHealthReport:
        """Return aggregate health for all configured required dependencies."""

        results = await asyncio.gather(
            *(self._run_one(check) for check in self._checks),
        )
        aggregate_status = (
            DependencyStatus.HEALTHY
            if all(result.status is DependencyStatus.HEALTHY for result in results)
            else DependencyStatus.UNHEALTHY
        )
        return DependencyHealthReport(status=aggregate_status, dependencies=tuple(results))

    async def _run_one(self, check: DependencyHealthCheck) -> DependencyHealthResult:
        task = asyncio.create_task(check.check())
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self._timeout_seconds)
        except TimeoutError:
            task.add_done_callback(_consume_task_exception)
            return DependencyHealthResult(
                name=check.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=self._timeout_seconds * 1000,
                detail=_SANITIZED_TIMEOUT_DETAIL,
            )
        except Exception:
            return DependencyHealthResult(
                name=check.name,
                status=DependencyStatus.UNHEALTHY,
                latency_ms=0,
                detail=_SANITIZED_FAILURE_DETAIL,
            )


def _consume_task_exception(task: asyncio.Task[DependencyHealthResult]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        return

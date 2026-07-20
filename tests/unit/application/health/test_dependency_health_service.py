"""Dependency health aggregation service tests."""

import asyncio

import pytest
from workflowforge_application.health import DependencyHealthService
from workflowforge_contracts import DependencyHealthResult, DependencyStatus


class FakeCheck:
    def __init__(
        self,
        name: str,
        status: DependencyStatus = DependencyStatus.HEALTHY,
        *,
        delay_seconds: float = 0,
        fail: bool = False,
    ) -> None:
        self.name = name
        self._status = status
        self._delay_seconds = delay_seconds
        self._fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def check(self) -> DependencyHealthResult:
        self.started.set()
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._fail:
            raise RuntimeError("raw driver details")
        if self.release.is_set():
            await self.release.wait()
        return DependencyHealthResult(
            name=self.name,
            status=self._status,
            latency_ms=1,
            detail=(
                "Dependency check failed." if self._status is DependencyStatus.UNHEALTHY else None
            ),
        )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((DependencyStatus.HEALTHY, DependencyStatus.HEALTHY), DependencyStatus.HEALTHY),
        ((DependencyStatus.HEALTHY, DependencyStatus.UNHEALTHY), DependencyStatus.UNHEALTHY),
        (
            (DependencyStatus.UNHEALTHY, DependencyStatus.UNHEALTHY),
            DependencyStatus.UNHEALTHY,
        ),
    ],
)
async def test_aggregates_dependency_status(
    statuses: tuple[DependencyStatus, ...],
    expected: DependencyStatus,
) -> None:
    service = DependencyHealthService(
        [FakeCheck(f"dependency_{index}", status) for index, status in enumerate(statuses)]
    )

    report = await service.check()

    assert report.status is expected


async def test_preserves_deterministic_result_order() -> None:
    service = DependencyHealthService(
        [
            FakeCheck("postgresql", delay_seconds=0.02),
            FakeCheck("redis"),
            FakeCheck("object_storage"),
        ]
    )

    report = await service.check()

    assert [result.name for result in report.dependencies] == [
        "postgresql",
        "redis",
        "object_storage",
    ]


async def test_unexpected_adapter_exception_is_sanitized() -> None:
    service = DependencyHealthService([FakeCheck("redis", fail=True)])

    report = await service.check()

    [result] = report.dependencies
    assert report.status is DependencyStatus.UNHEALTHY
    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "raw driver details" not in result.model_dump_json()


async def test_timeout_is_sanitized() -> None:
    service = DependencyHealthService(
        [FakeCheck("redis", delay_seconds=0.05)],
        timeout_seconds=0.01,
    )

    report = await service.check()

    [result] = report.dependencies
    assert report.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check timed out."
    assert result.latency_ms == 10


async def test_checks_run_concurrently() -> None:
    first = FakeCheck("first", delay_seconds=0.05)
    second = FakeCheck("second", delay_seconds=0.05)
    service = DependencyHealthService([first, second])

    task = asyncio.create_task(service.check())
    await asyncio.wait_for(first.started.wait(), timeout=1)
    await asyncio.wait_for(second.started.wait(), timeout=1)
    report = await task

    assert report.status is DependencyStatus.HEALTHY

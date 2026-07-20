"""Worker health check tests."""

from typing import Any, cast

from workflowforge_contracts import DependencyStatus
from workflowforge_infrastructure.tasks import WorkerHealthCheck


class FakeInspector:
    def __init__(self, replies: object = None, exc: Exception | None = None) -> None:
        self._replies = replies
        self._exc = exc

    def ping(self) -> object:
        if self._exc is not None:
            raise self._exc
        return self._replies


class FakeControl:
    def __init__(self, inspector: FakeInspector) -> None:
        self._inspector = inspector
        self.timeout: float | None = None

    def inspect(self, *, timeout: float) -> FakeInspector:
        self.timeout = timeout
        return self._inspector


class FakeCeleryApp:
    def __init__(self, inspector: FakeInspector) -> None:
        self.control = FakeControl(inspector)


async def test_worker_health_is_healthy_when_one_worker_responds() -> None:
    app = FakeCeleryApp(FakeInspector({"worker@host": {"ok": "pong"}}))

    result = await WorkerHealthCheck(cast("Any", app), timeout_seconds=1).check()

    assert result.name == "worker"
    assert result.status is DependencyStatus.HEALTHY
    assert result.detail == "1 worker responded."
    assert app.control.timeout == 0.5
    assert "worker@host" not in result.model_dump_json()


async def test_worker_health_is_unhealthy_when_no_worker_responds() -> None:
    app = FakeCeleryApp(FakeInspector(None))

    result = await WorkerHealthCheck(cast("Any", app), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "No workers responded."


async def test_worker_health_sanitizes_broker_failure() -> None:
    app = FakeCeleryApp(FakeInspector(exc=OSError("redis://secret")))

    result = await WorkerHealthCheck(cast("Any", app), timeout_seconds=1).check()

    assert result.status is DependencyStatus.UNHEALTHY
    assert result.detail == "Dependency check failed."
    assert "redis://secret" not in result.model_dump_json()

"""Dependency health endpoint tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from workflowforge_api.factory import create_app
from workflowforge_api.middleware import CORRELATION_ID_HEADER
from workflowforge_contracts import (
    DependencyHealthReport,
    DependencyHealthResult,
    DependencyStatus,
)
from workflowforge_infrastructure.config import Environment, Settings


class FakeDependencyHealthService:
    def __init__(self, report: DependencyHealthReport) -> None:
        self._report = report

    async def check(self) -> DependencyHealthReport:
        return self._report


def test_dependency_health_returns_200_when_all_dependencies_are_healthy() -> None:
    app = create_app(Settings(environment=Environment.TEST))
    app.state.dependency_health_service = FakeDependencyHealthService(
        DependencyHealthReport(
            status=DependencyStatus.HEALTHY,
            dependencies=(
                DependencyHealthResult(
                    name="postgresql",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=4.8,
                ),
                DependencyHealthResult(
                    name="redis",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=1.4,
                ),
                DependencyHealthResult(
                    name="object_storage",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=7.1,
                ),
                DependencyHealthResult(
                    name="worker",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=10.1,
                    detail="1 worker responded.",
                ),
                DependencyHealthResult(
                    name="scheduler",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=2.1,
                ),
            ),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/health/dependencies",
            headers={CORRELATION_ID_HEADER: "dependency-test"},
        )

    body = response.json()
    assert response.status_code == 200
    assert response.headers[CORRELATION_ID_HEADER] == "dependency-test"
    assert body["status"] == "healthy"
    assert datetime.fromisoformat(body["checked_at"]).tzinfo is not None
    assert datetime.fromisoformat(body["checked_at"]).astimezone(UTC).tzinfo is UTC
    assert list(body["dependencies"]) == [
        "postgresql",
        "redis",
        "object_storage",
        "worker",
        "scheduler",
    ]
    assert body["dependencies"]["worker"]["detail"] == "1 worker responded."


def test_dependency_health_returns_503_with_sanitized_unhealthy_dependency() -> None:
    app = create_app(Settings(environment=Environment.TEST))
    app.state.dependency_health_service = FakeDependencyHealthService(
        DependencyHealthReport(
            status=DependencyStatus.UNHEALTHY,
            dependencies=(
                DependencyHealthResult(
                    name="postgresql",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=4.8,
                ),
                DependencyHealthResult(
                    name="redis",
                    status=DependencyStatus.UNHEALTHY,
                    latency_ms=3000,
                    detail="Dependency check failed.",
                ),
            ),
        )
    )

    with TestClient(app) as client:
        response = client.get("/health/dependencies")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "unhealthy"
    assert body["dependencies"]["redis"] == {
        "status": "unhealthy",
        "latency_ms": 3000.0,
        "detail": "Dependency check failed.",
    }
    assert "redis://secret" not in response.text
    assert "Traceback" not in response.text


def test_dependency_health_returns_503_when_worker_is_unhealthy() -> None:
    app = create_app(Settings(environment=Environment.TEST))
    app.state.dependency_health_service = FakeDependencyHealthService(
        DependencyHealthReport(
            status=DependencyStatus.UNHEALTHY,
            dependencies=(
                DependencyHealthResult(
                    name="postgresql",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=4.8,
                ),
                DependencyHealthResult(
                    name="worker",
                    status=DependencyStatus.UNHEALTHY,
                    latency_ms=3000,
                    detail="No workers responded.",
                ),
            ),
        )
    )

    with TestClient(app) as client:
        response = client.get("/health/dependencies")

    body = response.json()
    assert response.status_code == 503
    assert body["dependencies"]["worker"]["detail"] == "No workers responded."


def test_dependency_health_returns_503_when_scheduler_is_unhealthy() -> None:
    app = create_app(Settings(environment=Environment.TEST))
    app.state.dependency_health_service = FakeDependencyHealthService(
        DependencyHealthReport(
            status=DependencyStatus.UNHEALTHY,
            dependencies=(
                DependencyHealthResult(
                    name="postgresql",
                    status=DependencyStatus.HEALTHY,
                    latency_ms=4.8,
                ),
                DependencyHealthResult(
                    name="scheduler",
                    status=DependencyStatus.UNHEALTHY,
                    latency_ms=1,
                    detail="Scheduler heartbeat is missing.",
                ),
            ),
        )
    )

    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")
        dependency_response = client.get("/health/dependencies")

    assert live_response.status_code == 200
    assert ready_response.status_code == 200
    assert dependency_response.status_code == 503
    assert dependency_response.json()["dependencies"]["scheduler"]["detail"] == (
        "Scheduler heartbeat is missing."
    )

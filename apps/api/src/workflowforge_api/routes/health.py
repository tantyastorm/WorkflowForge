"""Process-level health routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from workflowforge_application.health import DependencyHealthService
from workflowforge_contracts import DependencyHealthReport, DependencyStatus

from workflowforge_api.dependencies import (
    ReadinessState,
    get_dependency_health_service,
    get_readiness_state,
)
from workflowforge_api.schemas.health import (
    DependencyHealthResponse,
    DependencyHealthResponseItem,
    LiveHealthResponse,
    ReadyHealthResponse,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveHealthResponse)
async def live() -> LiveHealthResponse:
    """Return process liveness without dependency checks."""

    return LiveHealthResponse(status="ok", service="api")


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyHealthResponse}},
)
async def ready(
    response: Response,
    readiness: Annotated[ReadinessState, Depends(get_readiness_state)],
) -> ReadyHealthResponse:
    """Return whether FastAPI startup completed for this process."""

    if readiness.ready:
        return ReadyHealthResponse(status="ready", service="api")

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyHealthResponse(status="not_ready", service="api")


@router.get(
    "/dependencies",
    response_model=DependencyHealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": DependencyHealthResponse}},
)
async def dependencies(
    response: Response,
    health_service: Annotated[
        DependencyHealthService,
        Depends(get_dependency_health_service),
    ],
) -> DependencyHealthResponse:
    """Return real required dependency health."""

    report = await health_service.check()
    if report.status is DependencyStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return _dependency_health_response(report)


def _dependency_health_response(report: DependencyHealthReport) -> DependencyHealthResponse:
    return DependencyHealthResponse(
        status=report.status.value,
        checked_at=datetime.now(UTC),
        dependencies={
            result.name: DependencyHealthResponseItem(
                status=result.status.value,
                latency_ms=result.latency_ms,
                detail=result.detail,
            )
            for result in report.dependencies
        },
    )

"""Process-level health routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from workflowforge_api.dependencies import ReadinessState, get_readiness_state
from workflowforge_api.schemas.health import LiveHealthResponse, ReadyHealthResponse

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

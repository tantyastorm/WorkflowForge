"""FastAPI lifespan handling."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from workflowforge_api.dependencies import ReadinessState


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Mark readiness around local application startup and shutdown."""

    readiness = app.state.readiness
    if not isinstance(readiness, ReadinessState):
        msg = "Application readiness state is not configured."
        raise TypeError(msg)

    readiness.mark_ready()
    try:
        yield
    finally:
        readiness.mark_not_ready()

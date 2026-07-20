"""FastAPI lifespan handling."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from workflowforge_infrastructure.database import dispose_async_engine
from workflowforge_infrastructure.redis import close_redis_client
from workflowforge_infrastructure.storage import close_s3_client

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
        await dispose_async_engine(app.state.database_engine)
        await close_redis_client(app.state.redis_client)
        close_s3_client(app.state.s3_client)

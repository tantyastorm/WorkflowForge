"""API routes."""

from workflowforge_api.routes.auth import router as auth_router
from workflowforge_api.routes.health import router as health_router

__all__ = ["auth_router", "health_router"]

"""API routes."""

from workflowforge_api.routes.auth import router as auth_router
from workflowforge_api.routes.documents import router as documents_router
from workflowforge_api.routes.health import router as health_router
from workflowforge_api.routes.tenancy import router as tenancy_router

__all__ = ["auth_router", "documents_router", "health_router", "tenancy_router"]

"""FastAPI application factory."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workflowforge_infrastructure.config import Settings, get_settings
from workflowforge_infrastructure.logging import configure_logging

from workflowforge_api import __version__
from workflowforge_api.dependencies import ReadinessState, set_readiness_state
from workflowforge_api.exception_handlers import register_exception_handlers
from workflowforge_api.lifespan import lifespan
from workflowforge_api.middleware import RequestContextMiddleware
from workflowforge_api.routes import health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a fully wired FastAPI application instance."""

    resolved_settings = settings if settings is not None else get_settings()
    configure_logging(resolved_settings)

    docs_url = "/docs" if resolved_settings.api.docs_enabled else None
    redoc_url = "/redoc" if resolved_settings.api.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.api.docs_enabled else None

    app = FastAPI(
        title="WorkflowForge API",
        version=__version__,
        description="WorkflowForge backend API process.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.api_v1_prefix = resolved_settings.api.v1_prefix
    set_readiness_state(app.state, ReadinessState())

    app.add_middleware(
        RequestContextMiddleware,
        service="api",
        environment=resolved_settings.environment.value,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(APIRouter(prefix=resolved_settings.api.v1_prefix))

    return app

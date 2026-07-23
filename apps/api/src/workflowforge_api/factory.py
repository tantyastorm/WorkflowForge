"""FastAPI application factory."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workflowforge_application.health import DependencyHealthService
from workflowforge_application.health.service import DEFAULT_DEPENDENCY_TIMEOUT_SECONDS
from workflowforge_infrastructure.config import Environment, Settings, get_settings
from workflowforge_infrastructure.database import (
    DatabaseHealthCheck,
    create_async_database_engine,
)
from workflowforge_infrastructure.logging import configure_logging
from workflowforge_infrastructure.redis import RedisHealthCheck, create_redis_client
from workflowforge_infrastructure.storage import S3HealthCheck, create_s3_client
from workflowforge_infrastructure.tasks import (
    SchedulerHealthCheck,
    WorkerHealthCheck,
    create_celery_app,
)

from workflowforge_api import __version__
from workflowforge_api.dependencies import (
    ReadinessState,
    set_dependency_health_service,
    set_readiness_state,
)
from workflowforge_api.exception_handlers import register_exception_handlers
from workflowforge_api.lifespan import lifespan
from workflowforge_api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from workflowforge_api.routes import auth_router, documents_router, health_router, tenancy_router


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
    database_engine = create_async_database_engine(resolved_settings.database)
    redis_client = create_redis_client(resolved_settings.redis)
    s3_client = create_s3_client(resolved_settings.s3)
    celery_app = create_celery_app(resolved_settings)
    app.state.database_engine = database_engine
    app.state.redis_client = redis_client
    app.state.s3_client = s3_client
    app.state.celery_app = celery_app
    set_dependency_health_service(
        app.state,
        DependencyHealthService(
            (
                DatabaseHealthCheck(
                    database_engine,
                    timeout_seconds=DEFAULT_DEPENDENCY_TIMEOUT_SECONDS,
                ),
                RedisHealthCheck(redis_client),
                S3HealthCheck(s3_client, resolved_settings.s3),
                WorkerHealthCheck(
                    celery_app,
                    timeout_seconds=resolved_settings.celery.worker_health_timeout_seconds,
                ),
                SchedulerHealthCheck(
                    redis_client,
                    resolved_settings.scheduler,
                    timeout_seconds=resolved_settings.redis.socket_timeout_seconds,
                ),
            ),
            timeout_seconds=DEFAULT_DEPENDENCY_TIMEOUT_SECONDS,
        ),
    )

    app.add_middleware(
        RequestContextMiddleware,
        service="api",
        environment=resolved_settings.environment.value,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts_enabled=resolved_settings.environment is Environment.PRODUCTION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    api_router = APIRouter(prefix=resolved_settings.api.v1_prefix)
    api_router.include_router(auth_router)
    api_router.include_router(documents_router)
    api_router.include_router(tenancy_router)
    app.include_router(api_router)

    return app

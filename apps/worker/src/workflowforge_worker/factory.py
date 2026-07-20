"""Worker process composition."""

from typing import Any

from workflowforge_infrastructure.config import Settings, get_settings
from workflowforge_infrastructure.logging import configure_logging
from workflowforge_infrastructure.tasks import create_celery_app


def create_worker_app(settings: Settings | None = None) -> Any:
    """Create the Celery app used by the worker process."""

    resolved_settings = settings if settings is not None else get_settings()
    process_settings = resolved_settings.model_copy(update={"app_name": "worker"})
    configure_logging(process_settings)
    return create_celery_app(resolved_settings)

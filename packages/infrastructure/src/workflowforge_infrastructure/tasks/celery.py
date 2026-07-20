"""Celery application factory."""

import importlib
from typing import Any

from workflowforge_infrastructure.config import Settings, get_settings
from workflowforge_infrastructure.tasks.diagnostics import register_diagnostic_tasks
from workflowforge_infrastructure.tasks.schedules import register_periodic_schedules

CELERY_APP_NAME = "workflowforge"


def create_celery_app(settings: Settings | None = None) -> Any:
    """Create a configured Celery app without opening a broker connection."""

    resolved_settings = settings if settings is not None else get_settings()
    celery_module = importlib.import_module("celery")
    kombu_module = importlib.import_module("kombu")
    app = celery_module.Celery(CELERY_APP_NAME)
    app.conf.update(
        broker_url=resolved_settings.celery.resolved_broker_url(resolved_settings.redis),
        result_backend=resolved_settings.celery.resolved_result_backend(resolved_settings.redis),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        enable_utc=True,
        timezone="UTC",
        task_acks_late=False,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_time_limit=resolved_settings.celery.task_time_limit_seconds,
        task_soft_time_limit=resolved_settings.celery.task_soft_time_limit_seconds,
        task_default_queue=resolved_settings.celery.default_queue,
        task_queues=(
            kombu_module.Queue(resolved_settings.celery.default_queue),
            kombu_module.Queue(resolved_settings.celery.diagnostic_queue),
        ),
        task_routes={
            "system.diagnostics.*": {"queue": resolved_settings.celery.diagnostic_queue},
        },
        broker_connection_retry_on_startup=True,
        worker_hijack_root_logger=False,
        worker_concurrency=resolved_settings.celery.worker_concurrency,
        result_expires=3600,
    )
    register_diagnostic_tasks(app, resolved_settings)
    register_periodic_schedules(app, resolved_settings)
    return app

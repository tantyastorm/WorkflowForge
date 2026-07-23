"""Celery application factory."""

import importlib
from contextlib import suppress
from typing import Any

from workflowforge_infrastructure.config import Settings, get_settings
from workflowforge_infrastructure.tasks.diagnostics import register_diagnostic_tasks
from workflowforge_infrastructure.tasks.documents import register_document_tasks
from workflowforge_infrastructure.tasks.schedules import register_periodic_schedules
from workflowforge_infrastructure.tasks.security import register_security_tasks

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
    register_document_tasks(app, resolved_settings)
    register_security_tasks(app, resolved_settings)
    register_periodic_schedules(app, resolved_settings)
    return app


def close_celery_resources(app: Any, result: Any | None = None) -> None:
    """Release Celery client-side resources opened while publishing tasks."""

    if result is not None:
        with suppress(Exception):
            result.forget()

    backend = getattr(app, "backend", None)
    result_consumer = getattr(backend, "result_consumer", None)
    stop_result_consumer = getattr(result_consumer, "stop", None)
    if callable(stop_result_consumer):
        with suppress(Exception):
            stop_result_consumer()

    backend_client = getattr(backend, "client", None)
    close_backend_client = getattr(backend_client, "close", None)
    if callable(close_backend_client):
        with suppress(Exception):
            close_backend_client()

    backend_connection_pool = getattr(backend_client, "connection_pool", None)
    disconnect_backend_pool = getattr(backend_connection_pool, "disconnect", None)
    if callable(disconnect_backend_pool):
        with suppress(Exception):
            disconnect_backend_pool()

    for pool_name in ("pool", "producer_pool"):
        pool = getattr(app, pool_name, None)
        close_pool = getattr(pool, "force_close_all", None)
        if callable(close_pool):
            with suppress(Exception):
                close_pool()

    with suppress(Exception):
        app.close()

"""Celery task infrastructure."""

from workflowforge_infrastructure.tasks.celery import close_celery_resources, create_celery_app
from workflowforge_infrastructure.tasks.diagnostics import register_diagnostic_tasks
from workflowforge_infrastructure.tasks.health import SchedulerHealthCheck, WorkerHealthCheck
from workflowforge_infrastructure.tasks.schedules import register_periodic_schedules

__all__ = [
    "SchedulerHealthCheck",
    "WorkerHealthCheck",
    "close_celery_resources",
    "create_celery_app",
    "register_diagnostic_tasks",
    "register_periodic_schedules",
]

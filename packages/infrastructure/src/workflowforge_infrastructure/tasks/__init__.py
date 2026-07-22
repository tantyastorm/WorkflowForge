"""Celery task infrastructure."""

from workflowforge_infrastructure.tasks.celery import close_celery_resources, create_celery_app
from workflowforge_infrastructure.tasks.diagnostics import register_diagnostic_tasks
from workflowforge_infrastructure.tasks.health import SchedulerHealthCheck, WorkerHealthCheck
from workflowforge_infrastructure.tasks.schedules import register_periodic_schedules
from workflowforge_infrastructure.tasks.security import (
    SECURITY_CLEANUP_TASK_NAME,
    register_security_tasks,
)

__all__ = [
    "SchedulerHealthCheck",
    "WorkerHealthCheck",
    "close_celery_resources",
    "create_celery_app",
    "SECURITY_CLEANUP_TASK_NAME",
    "register_diagnostic_tasks",
    "register_periodic_schedules",
    "register_security_tasks",
]

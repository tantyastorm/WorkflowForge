"""Celery Beat schedule registration."""

from typing import Any

from workflowforge_contracts import SCHEDULER_HEARTBEAT_TASK_NAME

from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.tasks.security import SECURITY_CLEANUP_TASK_NAME

SCHEDULER_HEARTBEAT_SCHEDULE_NAME = "system-diagnostics-scheduler-heartbeat"
SECURITY_CLEANUP_SCHEDULE_NAME = "security-sessions-cleanup"


def register_periodic_schedules(app: Any, settings: Settings) -> None:
    """Register periodic diagnostic schedules on a Celery app."""

    schedule = {
        SCHEDULER_HEARTBEAT_SCHEDULE_NAME: {
            "task": SCHEDULER_HEARTBEAT_TASK_NAME,
            "schedule": settings.scheduler.heartbeat_interval_seconds,
            "options": {"queue": settings.celery.diagnostic_queue},
        }
    }
    if settings.cleanup.schedule_enabled:
        schedule[SECURITY_CLEANUP_SCHEDULE_NAME] = {
            "task": SECURITY_CLEANUP_TASK_NAME,
            "schedule": settings.cleanup.schedule_seconds,
            "options": {"queue": settings.celery.default_queue},
        }
    app.conf.beat_schedule = schedule

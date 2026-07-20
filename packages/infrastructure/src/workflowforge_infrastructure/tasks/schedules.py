"""Celery Beat schedule registration."""

from typing import Any

from workflowforge_contracts import SCHEDULER_HEARTBEAT_TASK_NAME

from workflowforge_infrastructure.config import Settings

SCHEDULER_HEARTBEAT_SCHEDULE_NAME = "system-diagnostics-scheduler-heartbeat"


def register_periodic_schedules(app: Any, settings: Settings) -> None:
    """Register periodic diagnostic schedules on a Celery app."""

    app.conf.beat_schedule = {
        SCHEDULER_HEARTBEAT_SCHEDULE_NAME: {
            "task": SCHEDULER_HEARTBEAT_TASK_NAME,
            "schedule": settings.scheduler.heartbeat_interval_seconds,
            "options": {"queue": settings.celery.diagnostic_queue},
        }
    }

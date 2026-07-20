"""Celery Beat CLI entry point."""

from workflowforge_scheduler.factory import create_scheduler_app

app = create_scheduler_app()

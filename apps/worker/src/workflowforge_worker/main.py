"""Celery worker CLI entry point."""

from workflowforge_worker.factory import create_worker_app

app = create_worker_app()

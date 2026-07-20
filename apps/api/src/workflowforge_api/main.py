"""Uvicorn entry point for the WorkflowForge API."""

from workflowforge_api.factory import create_app

app = create_app()

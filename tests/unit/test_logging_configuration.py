"""Logging configuration tests."""

from io import StringIO

import structlog
from workflowforge_infrastructure.config.settings import (
    Environment,
    LogFormat,
    LogLevel,
    Settings,
)
from workflowforge_infrastructure.logging import configure_logging


def test_configure_console_logging_outputs_context() -> None:
    stream = StringIO()
    settings = Settings(
        app_name="WorkflowForge Tests",
        environment=Environment.TEST,
        log_level=LogLevel.INFO,
        log_format=LogFormat.CONSOLE,
    )

    configure_logging(settings, stream=stream)

    structlog.get_logger("tests.console").info("workspace_ready")

    output = stream.getvalue()
    assert "workspace_ready" in output
    assert "WorkflowForge Tests" in output
    assert "test" in output
    assert "info" in output


def test_configure_json_logging_outputs_context() -> None:
    stream = StringIO()
    settings = Settings(
        app_name="WorkflowForge Tests",
        environment=Environment.TEST,
        log_level=LogLevel.INFO,
        log_format=LogFormat.JSON,
    )

    configure_logging(settings, stream=stream)

    structlog.get_logger("tests.json").info("workspace_ready")

    output = stream.getvalue()
    assert '"event": "workspace_ready"' in output
    assert '"service": "WorkflowForge Tests"' in output
    assert '"environment": "test"' in output
    assert '"level": "info"' in output


def test_repeated_logging_configuration_does_not_duplicate_output() -> None:
    stream = StringIO()
    settings = Settings(environment=Environment.TEST)

    configure_logging(settings, stream=stream)
    configure_logging(settings, stream=stream)

    structlog.get_logger("tests.repeat").warning("called_once")

    assert stream.getvalue().count("called_once") == 1

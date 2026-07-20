"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from typing import TextIO, cast

import structlog

from workflowforge_infrastructure.config.settings import LogFormat, Settings

Processor = structlog.types.Processor


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure standard-library logging and structlog.

    The function is idempotent for a process: it replaces root handlers instead of
    appending to them, which prevents duplicate log lines when called repeatedly.
    """

    output = stream if stream is not None else sys.stderr

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: Sequence[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        _add_service_context(settings),
    ]

    renderer: Processor
    if settings.log_format is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(output)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level.value)

    structlog.configure(
        processors=[
            *cast("tuple[Processor, ...]", tuple(shared_processors)),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _add_service_context(settings: Settings) -> Processor:
    def processor(
        _logger: logging.Logger,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        event_dict["service"] = settings.app_name
        event_dict["environment"] = settings.environment.value
        return event_dict

    return processor

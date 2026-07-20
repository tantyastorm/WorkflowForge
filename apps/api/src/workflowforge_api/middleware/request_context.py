"""Correlation ID and request logging middleware."""

from __future__ import annotations

import re
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

CORRELATION_ID_HEADER = "X-Correlation-ID"
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:/@+-]{1,128}$")


def current_correlation_id() -> str | None:
    """Return the request-local correlation ID, when one is bound."""

    context = structlog.contextvars.get_contextvars()
    value = context.get("correlation_id")
    return value if isinstance(value, str) else None


def normalize_correlation_id(value: str | None) -> str:
    """Return a safe incoming correlation ID or generate a replacement."""

    if value is not None and _SAFE_CORRELATION_ID.fullmatch(value):
        return value
    return str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind request-local context and emit structured request completion logs."""

    def __init__(self, app: ASGIApp, *, service: str, environment: str) -> None:
        super().__init__(app)
        self._service = service
        self._environment = environment
        self._logger = structlog.get_logger("workflowforge_api.request")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = normalize_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        started_at = perf_counter()
        status_code = 500
        response: Response | None = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            self._logger.info(
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
                service=self._service,
                environment=self._environment,
            )
            if response is not None:
                response.headers[CORRELATION_ID_HEADER] = correlation_id
            structlog.contextvars.clear_contextvars()

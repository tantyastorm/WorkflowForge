"""Global API exception handlers."""

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from workflowforge_application.errors import ApplicationError
from workflowforge_domain.errors import DomainError

from workflowforge_api.middleware import current_correlation_id
from workflowforge_api.schemas.errors import ErrorDetail, ErrorResponse

_LOGGER = structlog.get_logger("workflowforge_api.errors")


class ApiError(Exception):
    """Transport-level API error with a stable public response."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent API error responses."""

    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(ApplicationError, _known_application_error_handler)
    app.add_exception_handler(DomainError, _known_application_error_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        raise TypeError
    correlation_id = _correlation_id(request)
    _LOGGER.info(
        "api_error",
        error_code=exc.code,
        status_code=exc.status_code,
        correlation_id=correlation_id,
    )
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        correlation_id=correlation_id,
        headers=exc.headers,
    )


async def _known_application_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    correlation_id = _correlation_id(_request)
    _LOGGER.info(
        "known_application_error",
        error_type=type(exc).__name__,
        correlation_id=correlation_id,
    )
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="application_error",
        message="The request could not be processed.",
        correlation_id=correlation_id,
    )


async def _request_validation_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    correlation_id = _correlation_id(_request)
    error_count = len(exc.errors()) if isinstance(exc, RequestValidationError) else 0
    _LOGGER.info(
        "request_validation_error",
        error_count=error_count,
        correlation_id=correlation_id,
    )
    return _error_response(
        status_code=422,
        code="validation_error",
        message="The request is invalid.",
        correlation_id=correlation_id,
    )


async def _unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    correlation_id = _correlation_id(_request)
    _LOGGER.exception(
        "unexpected_application_error",
        error_type=type(exc).__name__,
        correlation_id=correlation_id,
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred.",
        correlation_id=correlation_id,
    )


def _correlation_id(request: Request) -> str | None:
    context_correlation_id = current_correlation_id()
    if context_correlation_id is not None:
        return context_correlation_id
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) else None


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str | None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=correlation_id,
        )
    ).model_dump()
    return JSONResponse(status_code=status_code, content=content, headers=headers)

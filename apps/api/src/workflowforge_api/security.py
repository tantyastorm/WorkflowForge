"""HTTP authentication and CSRF helpers."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Request, Response
from workflowforge_infrastructure.config import AuthSettings, Settings


@dataclass(frozen=True, slots=True)
class CsrfTokenGenerator:
    """Generate browser double-submit CSRF tokens."""

    token_bytes: int = 32

    def generate(self) -> str:
        """Return a URL-safe CSRF token."""

        return secrets.token_urlsafe(self.token_bytes)


def validate_origin(request: Request, settings: Settings) -> None:
    """Reject cross-origin cookie-authenticated mutations."""

    origin = request.headers.get("origin")
    if origin is None:
        return
    incoming_origin = _parse_origin(origin)
    allowed_origins = {_parse_origin(value) for value in settings.cors_origins}
    if incoming_origin not in allowed_origins:
        raise CsrfValidationError


def validate_csrf(request: Request, settings: AuthSettings) -> None:
    """Require double-submit cookie and header equality."""

    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    header_value = request.headers.get(settings.csrf_header_name)
    if not cookie_value or not header_value:
        raise CsrfValidationError
    if not hmac.compare_digest(cookie_value, header_value):
        raise CsrfValidationError


def set_refresh_cookie(
    response: Response,
    settings: AuthSettings,
    value: str,
    *,
    max_age: int,
) -> None:
    """Set the HttpOnly refresh-token cookie."""

    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=value,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def set_csrf_cookie(
    response: Response,
    settings: AuthSettings,
    value: str,
    *,
    max_age: int,
) -> None:
    """Set the readable double-submit CSRF cookie."""

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=value,
        max_age=max_age,
        path="/",
        secure=settings.refresh_cookie_secure,
        httponly=False,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_auth_cookies(response: Response, settings: AuthSettings) -> None:
    """Clear refresh and CSRF cookies."""

    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.refresh_cookie_secure,
        httponly=False,
        samesite=settings.refresh_cookie_samesite,
    )


class CsrfValidationError(Exception):
    """Raised when a cookie-authenticated request fails CSRF validation."""


def _parse_origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CsrfValidationError
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise CsrfValidationError
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

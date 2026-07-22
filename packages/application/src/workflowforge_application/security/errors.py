"""Security hardening application errors."""

from dataclasses import dataclass

from workflowforge_application.errors import ApplicationError


class SecurityApplicationError(ApplicationError):
    """Base class for security hardening application errors."""


class BootstrapRefusedError(SecurityApplicationError):
    """Raised when first-owner bootstrap is not allowed."""


class RateLimitUnavailableError(SecurityApplicationError):
    """Raised when rate-limit state cannot be checked."""


@dataclass(frozen=True, slots=True)
class RateLimitExceededError(SecurityApplicationError):
    """Raised when a security rate limit denies a request."""

    retry_after_seconds: int

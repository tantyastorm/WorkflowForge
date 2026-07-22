"""Authentication rate-limit helpers."""

from dataclasses import dataclass

from workflowforge_application.security.errors import RateLimitExceededError
from workflowforge_application.security.ports import AuthenticationRateLimiter


@dataclass(frozen=True, slots=True)
class RateLimitIdentity:
    """Safe rate-limit identity."""

    normalized_identifier: str
    client_key: str | None


async def require_login_allowed(
    limiter: AuthenticationRateLimiter,
    identity: RateLimitIdentity,
) -> None:
    """Raise when login is rate-limited."""

    decision = await limiter.check_login_allowed(
        normalized_identifier=identity.normalized_identifier,
        client_key=identity.client_key,
    )
    if not decision.allowed:
        raise RateLimitExceededError(decision.retry_after_seconds)


async def require_refresh_allowed(
    limiter: AuthenticationRateLimiter,
    *,
    client_key: str | None,
) -> None:
    """Raise when refresh is rate-limited."""

    decision = await limiter.check_refresh_allowed(client_key=client_key)
    if not decision.allowed:
        raise RateLimitExceededError(decision.retry_after_seconds)

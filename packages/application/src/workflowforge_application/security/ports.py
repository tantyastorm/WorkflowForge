"""Security hardening application ports."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BootstrapState:
    """Minimal identity initialization state."""

    users: int
    organizations: int

    @property
    def initialized(self) -> bool:
        """Return whether identity state already exists."""

        return self.users > 0 or self.organizations > 0


class IdentityBootstrapRepository(Protocol):
    """Narrow query port for first-owner bootstrap guards."""

    async def acquire_bootstrap_lock(self) -> None:
        """Serialize bootstrap state checks within the current transaction."""

    async def bootstrap_state(self) -> BootstrapState:
        """Return current user and organization counts."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of a rate-limit check."""

    allowed: bool
    retry_after_seconds: int = 0


class AuthenticationRateLimiter(Protocol):
    """Narrow rate limiter for authentication-sensitive endpoints."""

    async def check_login_allowed(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        """Return whether a login attempt may proceed."""

    async def record_login_failure(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        """Record a failed login attempt and return the current decision."""

    async def record_login_success(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> None:
        """Clear login failure state after a successful login."""

    async def check_refresh_allowed(self, *, client_key: str | None) -> RateLimitDecision:
        """Return whether a refresh attempt may proceed."""

    async def record_refresh_failure(self, *, client_key: str | None) -> RateLimitDecision:
        """Record a failed refresh attempt and return the current decision."""

    async def record_refresh_success(self, *, client_key: str | None) -> None:
        """Clear refresh failure state after successful refresh."""


@dataclass(frozen=True, slots=True)
class SessionCleanupResult:
    """Counts returned by session cleanup."""

    expired_refresh_tokens_deleted: int
    expired_sessions_deleted: int
    revoked_sessions_deleted: int


class SessionCleanupRepository(Protocol):
    """Persistence operations for bounded session cleanup."""

    async def delete_expired_refresh_tokens(self, *, before: datetime, limit: int) -> int:
        """Delete expired refresh-token records in a bounded batch."""

    async def delete_expired_sessions(self, *, before: datetime, limit: int) -> int:
        """Delete expired sessions in a bounded batch."""

    async def delete_revoked_sessions(self, *, before: datetime, limit: int) -> int:
        """Delete old revoked sessions in a bounded batch."""

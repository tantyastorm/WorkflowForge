"""Redis-backed authentication rate limiter."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable
from typing import Any, Protocol

from redis.exceptions import RedisError
from workflowforge_application.security import AuthenticationRateLimiter, RateLimitDecision
from workflowforge_application.security.errors import RateLimitUnavailableError

from workflowforge_infrastructure.config import RateLimitFailurePolicy, RateLimitSettings

_SAFE_CLIENT_KEY = re.compile(r"[^A-Za-z0-9_.:-]")
_INCREMENT_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


class RedisRateLimitClient(Protocol):
    """Redis command surface used by the authentication limiter."""

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Awaitable[Any]:
        """Evaluate a Redis script."""

    def get(self, name: Any) -> Awaitable[Any]:
        """Return a Redis value."""

    def ttl(self, name: Any) -> Awaitable[int]:
        """Return a Redis key TTL."""

    def delete(self, *names: Any) -> Awaitable[Any]:
        """Delete Redis keys."""


class RedisAuthenticationRateLimiter(AuthenticationRateLimiter):
    """Fixed-window Redis rate limiter for login and refresh abuse protection."""

    def __init__(self, client: RedisRateLimitClient, settings: RateLimitSettings) -> None:
        self._client = client
        self._settings = settings

    async def check_login_allowed(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        """Return whether login may proceed without changing counters."""

        return await self._combined_decision(
            (
                _login_identifier_key(normalized_identifier),
                self._settings.login_identifier_threshold,
                self._settings.login_window_seconds,
            ),
            (
                _login_client_key(client_key),
                self._settings.login_client_threshold,
                self._settings.login_window_seconds,
            ),
            increment=False,
        )

    async def record_login_failure(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        """Record failed login and return current decision."""

        return await self._combined_decision(
            (
                _login_identifier_key(normalized_identifier),
                self._settings.login_identifier_threshold,
                self._settings.login_window_seconds,
            ),
            (
                _login_client_key(client_key),
                self._settings.login_client_threshold,
                self._settings.login_window_seconds,
            ),
            increment=True,
        )

    async def record_login_success(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> None:
        """Clear login failure counters."""

        await self._delete(
            _login_identifier_key(normalized_identifier),
            _login_client_key(client_key),
        )

    async def check_refresh_allowed(self, *, client_key: str | None) -> RateLimitDecision:
        """Return whether refresh may proceed."""

        return await self._decision(
            key=_refresh_client_key(client_key),
            threshold=self._settings.refresh_client_threshold,
            window_seconds=self._settings.refresh_window_seconds,
            increment=False,
        )

    async def record_refresh_failure(self, *, client_key: str | None) -> RateLimitDecision:
        """Record failed refresh and return current decision."""

        return await self._decision(
            key=_refresh_client_key(client_key),
            threshold=self._settings.refresh_client_threshold,
            window_seconds=self._settings.refresh_window_seconds,
            increment=True,
        )

    async def record_refresh_success(self, *, client_key: str | None) -> None:
        """Clear refresh failure counters."""

        await self._delete(_refresh_client_key(client_key))

    async def _combined_decision(
        self,
        first: tuple[str, int, int],
        second: tuple[str, int, int],
        *,
        increment: bool,
    ) -> RateLimitDecision:
        first_decision = await self._decision(
            key=first[0],
            threshold=first[1],
            window_seconds=first[2],
            increment=increment,
        )
        second_decision = await self._decision(
            key=second[0],
            threshold=second[1],
            window_seconds=second[2],
            increment=increment,
        )
        if first_decision.allowed and second_decision.allowed:
            return RateLimitDecision(allowed=True)
        return RateLimitDecision(
            allowed=False,
            retry_after_seconds=max(
                first_decision.retry_after_seconds,
                second_decision.retry_after_seconds,
            ),
        )

    async def _decision(
        self,
        *,
        key: str,
        threshold: int,
        window_seconds: int,
        increment: bool,
    ) -> RateLimitDecision:
        try:
            if increment:
                count, ttl = await self._increment_window(key, window_seconds)
            else:
                value = await self._client.get(key)
                count = int(value) if value is not None else 0
                ttl = await self._client.ttl(key)
        except RedisError as exc:
            return self._redis_failure(exc)

        if count < threshold:
            return RateLimitDecision(allowed=True)
        retry_after = ttl if ttl and ttl > 0 else window_seconds
        return RateLimitDecision(allowed=False, retry_after_seconds=int(retry_after))

    async def _delete(self, *keys: str) -> None:
        try:
            await self._client.delete(*keys)
        except RedisError as exc:
            self._redis_failure(exc)

    async def _increment_window(self, key: str, window_seconds: int) -> tuple[int, int]:
        result = await self._client.eval(_INCREMENT_WINDOW_SCRIPT, 1, key, window_seconds)
        count, ttl = result
        return int(count), int(ttl)

    def _redis_failure(self, exc: RedisError) -> RateLimitDecision:
        if self._settings.failure_policy is RateLimitFailurePolicy.OPEN:
            return RateLimitDecision(allowed=True)
        msg = "Rate-limit backend is unavailable."
        raise RateLimitUnavailableError(msg) from exc


def _login_identifier_key(identifier: str) -> str:
    return "workflowforge:ratelimit:login:identifier:" + _hash(identifier)


def _login_client_key(client_key: str | None) -> str:
    return "workflowforge:ratelimit:login:client:" + _safe_client(client_key)


def _refresh_client_key(client_key: str | None) -> str:
    return "workflowforge:ratelimit:refresh:client:" + _safe_client(client_key)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_client(value: str | None) -> str:
    if not value:
        return "unknown"
    return _hash(_SAFE_CLIENT_KEY.sub("_", value[:128]))

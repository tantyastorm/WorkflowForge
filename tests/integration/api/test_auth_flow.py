"""Authentication API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from workflowforge_api.factory import create_app
from workflowforge_application.identity import SetUserPassword, SetUserPasswordCommand
from workflowforge_domain.audit import AuditEventType
from workflowforge_domain.identity import EmailAddress, User
from workflowforge_infrastructure.audit.models import SecurityAuditEventRecord
from workflowforge_infrastructure.config import (
    Environment,
    RateLimitSettings,
    RedisSettings,
    Settings,
)
from workflowforge_infrastructure.database import (
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    Argon2PasswordHasher,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemyUserRepository,
)
from workflowforge_infrastructure.identity.models import AuthSessionRecord
from workflowforge_infrastructure.redis import close_redis_client, create_redis_client

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
PASSWORD = "correct horse battery staple"


@pytest.mark.integration
def test_auth_http_lifecycle_with_refresh_replay_revocation() -> None:
    settings = _settings()
    _reset_database()
    _seed_user(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        first_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
        )

        assert first_login.status_code == 200
        _assert_refresh_cookie(
            _set_cookies(first_login),
            value=first_login.cookies["workflowforge_refresh"],
        )
        _assert_csrf_cookie(_set_cookies(first_login))
        assert "refresh_token" not in first_login.json()
        first_access = first_login.json()["access_token"]
        first_refresh = first_login.cookies["workflowforge_refresh"]
        first_csrf = first_login.cookies["workflowforge_csrf"]

        first_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {first_access}"},
        )
        assert first_me.status_code == 200

        refresh = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": first_csrf},
        )
        assert refresh.status_code == 200
        assert "refresh_token" not in refresh.json()
        _assert_refresh_cookie(
            _set_cookies(refresh),
            value=refresh.cookies["workflowforge_refresh"],
        )
        _assert_csrf_cookie(_set_cookies(refresh))
        rotated_access = refresh.json()["access_token"]
        rotated_csrf = refresh.cookies["workflowforge_csrf"]

        old_csrf_after_rotation = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": first_csrf},
        )
        assert old_csrf_after_rotation.status_code == 403

        second_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
        )
        assert second_login.status_code == 200
        second_access = second_login.json()["access_token"]

        replay = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": rotated_csrf,
                "Cookie": _auth_cookie_header(refresh=first_refresh, csrf=rotated_csrf),
            },
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "authentication_failed"
        _assert_cleared_cookie(_set_cookies(replay), "workflowforge_refresh", httponly=True)
        _assert_cleared_cookie(_set_cookies(replay), "workflowforge_csrf", httponly=False)

        revoked_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {rotated_access}"},
        )
        unaffected_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {second_access}"},
        )
        assert revoked_me.status_code == 401
        assert unaffected_me.status_code == 200


@pytest.mark.integration
def test_auth_logout_and_logout_all_http_contracts() -> None:
    settings = _settings()
    _reset_database()
    _seed_user(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        first_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
        )
        first_access = first_login.json()["access_token"]
        first_refresh = first_login.cookies["workflowforge_refresh"]
        first_csrf = first_login.cookies["workflowforge_csrf"]

        second_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
        )
        assert first_login.status_code == 200
        assert second_login.status_code == 200
        second_access = second_login.json()["access_token"]

        logout = client.post(
            "/api/v1/auth/logout",
            headers={
                "Authorization": f"Bearer {first_access}",
                "X-CSRF-Token": first_csrf,
                "Cookie": _auth_cookie_header(refresh=first_refresh, csrf=first_csrf),
            },
        )
        assert logout.status_code == 200
        _assert_cleared_cookie(_set_cookies(logout), "workflowforge_refresh", httponly=True)
        _assert_cleared_cookie(_set_cookies(logout), "workflowforge_csrf", httponly=False)
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {first_access}"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {second_access}"},
            ).status_code
            == 200
        )

        third_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": PASSWORD},
        )
        assert third_login.status_code == 200
        third_access = third_login.json()["access_token"]
        second_csrf = second_login.cookies["workflowforge_csrf"]

        logout_all = client.post(
            "/api/v1/auth/logout-all",
            headers={
                "Authorization": f"Bearer {second_access}",
                "X-CSRF-Token": second_csrf,
                "Cookie": _auth_cookie_header(
                    refresh=second_login.cookies["workflowforge_refresh"],
                    csrf=second_csrf,
                ),
            },
        )
        assert logout_all.status_code == 200
        assert logout_all.json()["revoked_sessions"] == 2
        _assert_cleared_cookie(_set_cookies(logout_all), "workflowforge_refresh", httponly=True)
        _assert_cleared_cookie(_set_cookies(logout_all), "workflowforge_csrf", httponly=False)
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {second_access}"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {third_access}"},
            ).status_code
            == 401
        )


@pytest.mark.integration
def test_invalid_login_audit_persists_after_401_without_session_state() -> None:
    settings = _settings()
    _reset_database()
    _seed_user(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "wrong password"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
    assert _audit_count(settings, AuditEventType.AUTHENTICATION_LOGIN_FAILED) == 1
    assert _session_count(settings) == 0


@pytest.mark.integration
def test_invalid_login_attempts_are_rate_limited_with_real_redis() -> None:
    settings = Settings(
        environment=Environment.TEST,
        database=require_postgresql(),
        redis=_redis_settings(),
        rate_limit=RateLimitSettings(
            login_identifier_threshold=2,
            login_client_threshold=20,
            login_window_seconds=60,
        ),
    )
    _reset_database()
    _clear_rate_limit_keys(settings)
    _seed_user(settings)
    app = create_app(settings)

    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/auth/login",
                json={"email": "ada@example.com", "password": "wrong password"},
            )
            second = client.post(
                "/api/v1/auth/login",
                json={"email": "ADA@example.com", "password": "wrong password"},
            )
            third = client.post(
                "/api/v1/auth/login",
                json={"email": "ada@example.com", "password": "wrong password"},
            )

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.headers["retry-after"] == "60"
        assert third.json()["error"]["code"] == "rate_limited"
        assert "set-cookie" not in third.headers
        assert _audit_count(settings, AuditEventType.AUTHENTICATION_LOGIN_RATE_LIMITED) == 1
        assert _session_count(settings) == 0
    finally:
        _clear_rate_limit_keys(settings)


def _settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        database=require_postgresql(),
        redis=_redis_settings(),
    )


def _reset_database() -> None:
    command.downgrade(_alembic_config(), "base")
    command.upgrade(_alembic_config(), "head")


def _seed_user(settings: Settings) -> None:
    import asyncio

    asyncio.run(_seed_user_async(settings))


async def _seed_user_async(settings: Settings) -> None:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        users = SqlAlchemyUserRepository(session)
        credentials = SqlAlchemyPasswordCredentialRepository(session)
        await users.add(
            User.create(
                id=USER_ID,
                email=EmailAddress("ada@example.com"),
                display_name="Ada Lovelace",
                now=NOW,
            )
        )
        set_password = SetUserPassword(
            users=users,
            credentials=credentials,
            password_hasher=Argon2PasswordHasher(),
        )
        await set_password(SetUserPasswordCommand(user_id=USER_ID, password=PASSWORD), now=NOW)
        await session.commit()
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _audit_count(settings: Settings, event_type: AuditEventType) -> int:
    import asyncio

    return asyncio.run(_audit_count_async(settings, event_type))


async def _audit_count_async(settings: Settings, event_type: AuditEventType) -> int:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        result = await session.execute(
            select(func.count())
            .select_from(SecurityAuditEventRecord)
            .where(SecurityAuditEventRecord.event_type == event_type.value)
        )
        return int(result.scalar_one())
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _session_count(settings: Settings) -> int:
    import asyncio

    return asyncio.run(_session_count_async(settings))


async def _session_count_async(settings: Settings) -> int:
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        result = await session.execute(select(func.count()).select_from(AuthSessionRecord))
        return int(result.scalar_one())
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _redis_settings() -> RedisSettings:
    import os

    return RedisSettings(
        host=os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST", "localhost"),
        port=int(os.environ.get("WORKFLOWFORGE_TEST_REDIS_HOST_PORT", "6379")),
    )


def _clear_rate_limit_keys(settings: Settings) -> None:
    import asyncio

    asyncio.run(_clear_rate_limit_keys_async(settings))


async def _clear_rate_limit_keys_async(settings: Settings) -> None:
    client = create_redis_client(settings.redis)
    try:
        keys = [str(key) async for key in client.scan_iter("workflowforge:ratelimit:*")]
        if keys:
            await client.delete(*keys)
    finally:
        await close_redis_client(client)


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = require_postgresql()
    return config


def _auth_cookie_header(*, refresh: str, csrf: str) -> str:
    return f"workflowforge_refresh={refresh}; workflowforge_csrf={csrf}"


def _set_cookies(response: Any) -> dict[str, dict[str, str | bool]]:
    headers = response.headers.get_list("set-cookie")
    parsed: dict[str, dict[str, str | bool]] = {}
    for header in headers:
        cookie = SimpleCookie()
        cookie.load(header)
        for name, morsel in cookie.items():
            parsed[name] = {
                "value": morsel.value,
                "path": morsel["path"],
                "max-age": morsel["max-age"],
                "samesite": morsel["samesite"],
                "secure": bool(morsel["secure"]),
                "httponly": bool(morsel["httponly"]),
                "domain": morsel["domain"],
            }
    return parsed


def _assert_refresh_cookie(cookies: dict[str, dict[str, str | bool]], *, value: str) -> None:
    cookie = cookies["workflowforge_refresh"]
    assert cookie["value"] == value
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["max-age"] == "2592000"
    assert cookie["samesite"] == "lax"
    assert cookie["httponly"] is True
    assert cookie["secure"] is False
    assert cookie["domain"] == ""


def _assert_csrf_cookie(cookies: dict[str, dict[str, str | bool]]) -> None:
    cookie = cookies["workflowforge_csrf"]
    assert cookie["value"]
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["max-age"] == "2592000"
    assert cookie["samesite"] == "lax"
    assert cookie["httponly"] is False
    assert cookie["secure"] is False
    assert cookie["domain"] == ""


def _assert_cleared_cookie(
    cookies: dict[str, dict[str, str | bool]],
    name: str,
    *,
    httponly: bool,
) -> None:
    cookie = cookies[name]
    assert cookie["value"] == ""
    assert cookie["path"] == "/api/v1/auth"
    assert cookie["max-age"] == "0"
    assert cookie["samesite"] == "lax"
    assert cookie["httponly"] is httponly
    assert cookie["secure"] is False
    assert cookie["domain"] == ""

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
from workflowforge_api.factory import create_app
from workflowforge_application.identity import SetUserPassword, SetUserPasswordCommand
from workflowforge_domain.identity import EmailAddress, User
from workflowforge_infrastructure.config import Environment, Settings
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


def _settings() -> Settings:
    return Settings(environment=Environment.TEST, database=require_postgresql())


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

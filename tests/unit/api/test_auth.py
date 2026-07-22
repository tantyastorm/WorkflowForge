"""Authentication route tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from workflowforge_api.dependencies import (
    get_authentication_rate_limiter,
    get_current_principal,
    get_independent_audit_recorder,
    get_logout_all_sessions,
    get_logout_session,
    get_refresh_session,
    get_start_user_session,
    get_verify_access_token,
)
from workflowforge_api.factory import create_app
from workflowforge_application.identity import (
    AccessTokenClaims,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LogoutAllSessionsCommand,
    LogoutAllSessionsResult,
    LogoutSessionCommand,
    RefreshSessionCommand,
    StartUserSessionCommand,
    TokenPair,
    VerifiedAccessPrincipal,
)
from workflowforge_application.security import (
    AuthenticationRateLimiter,
    RateLimitDecision,
    RateLimitUnavailableError,
)
from workflowforge_domain.audit import AuditEvent
from workflowforge_domain.identity import SessionId
from workflowforge_infrastructure.config import Environment, Settings

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("77777777-7777-4777-8777-777777777777")


def test_login_success_sets_refresh_and_csrf_cookies_without_refresh_json() -> None:
    app = _app()
    start = FakeStartUserSession(_token_pair("access-1", "refresh-1"))
    app.dependency_overrides[get_start_user_session] = lambda: start

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "correct horse"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "access-1"
    assert body["token_type"] == "Bearer"
    assert body["session_id"] == str(SESSION_ID)
    assert "refresh_token" not in body
    assert start.commands[0].email == "ada@example.com"
    assert start.commands[0].password == "correct horse"
    assert start.commands[0].audit_context is not None
    assert start.commands[0].audit_context.user_agent == "testclient"
    cookies = _set_cookies(response)
    _assert_refresh_cookie(cookies, value="refresh-1")
    _assert_csrf_cookie(cookies)


def test_login_rejects_untrusted_origin_without_requiring_csrf() -> None:
    app = _app()
    start = FakeStartUserSession(_token_pair("access-1", "refresh-1"))
    app.dependency_overrides[get_start_user_session] = lambda: start

    with TestClient(app) as client:
        trusted = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": "ada@example.com", "password": "correct horse"},
        )
        untrusted = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://trusted.example.attacker.com"},
            json={"email": "ada@example.com", "password": "correct horse"},
        )

    assert trusted.status_code == 200
    assert untrusted.status_code == 403
    assert untrusted.json()["error"]["code"] == "csrf_failed"


def test_login_invalid_credentials_returns_401_without_cookies() -> None:
    app = _app()
    app.dependency_overrides[get_start_user_session] = lambda: FakeStartUserSession(
        InvalidCredentialsError("Invalid")
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "bad password"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "authentication_failed"
    assert "set-cookie" not in response.headers


def test_login_rate_limit_returns_429_without_authentication_attempt() -> None:
    app = _app()
    start = FakeStartUserSession(_token_pair("access-1", "refresh-1"))
    limiter = FakeAuthenticationRateLimiter(login_allowed=RateLimitDecision(False, 42))
    app.dependency_overrides[get_start_user_session] = lambda: start
    app.dependency_overrides[get_authentication_rate_limiter] = lambda: limiter

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "Ada@Example.COM", "password": "bad password"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.json()["error"]["code"] == "rate_limited"
    assert start.commands == []
    assert limiter.login_checks == [("ada@example.com", "testclient")]


def test_login_rate_limit_audit_failure_preserves_public_429() -> None:
    app = _app()
    limiter = FakeAuthenticationRateLimiter(login_allowed=RateLimitDecision(False, 42))
    app.dependency_overrides[get_authentication_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_independent_audit_recorder] = FailingAuditRecorder

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "bad password"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.json()["error"]["code"] == "rate_limited"


def test_login_audit_failure_preserves_public_401_response() -> None:
    app = _app()
    app.dependency_overrides[get_start_user_session] = lambda: FakeStartUserSession(
        InvalidCredentialsError("Invalid")
    )
    app.dependency_overrides[get_independent_audit_recorder] = FailingAuditRecorder

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "bad password"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_login_failure_rate_limit_backend_error_returns_429() -> None:
    app = _app()
    limiter = FakeAuthenticationRateLimiter(raise_on_login_failure=True)
    app.dependency_overrides[get_start_user_session] = lambda: FakeStartUserSession(
        InvalidCredentialsError("Invalid")
    )
    app.dependency_overrides[get_authentication_rate_limiter] = lambda: limiter

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "bad password"},
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["error"]["code"] == "rate_limited"


def test_refresh_requires_cookie_and_csrf() -> None:
    app = _app()
    app.dependency_overrides[get_refresh_session] = lambda: FakeRefreshSession(
        _token_pair("access-2", "refresh-2")
    )

    with TestClient(app) as client:
        missing_cookie = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": "csrf", "Cookie": "workflowforge_csrf=csrf"},
        )
        missing_csrf = client.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf")},
        )
        mismatched_csrf = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "other",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )
        empty_header = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )
        empty_cookie = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf=""),
            },
        )
        untrusted_origin = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf",
                "Origin": "https://trusted.example.attacker.com",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )
        null_origin = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf",
                "Origin": "null",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )
        wrong_port_origin = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf",
                "Origin": "http://localhost:444",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )
        malformed_origin = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf",
                "Origin": "http://localhost:5173/path",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf"),
            },
        )

    assert missing_cookie.status_code == 401
    assert missing_csrf.status_code == 403
    assert mismatched_csrf.status_code == 403
    assert empty_header.status_code == 403
    assert empty_cookie.status_code == 403
    assert untrusted_origin.status_code == 403
    assert null_origin.status_code == 403
    assert wrong_port_origin.status_code == 403
    assert malformed_origin.status_code == 403


def test_refresh_success_rotates_refresh_and_csrf_cookies() -> None:
    app = _app()
    refresh = FakeRefreshSession(_token_pair("access-2", "refresh-2"))
    app.dependency_overrides[get_refresh_session] = lambda: refresh

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf-1",
                "Origin": "http://localhost:5173",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf-1"),
            },
        )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access-2"
    assert "refresh_token" not in response.json()
    assert refresh.commands[0].refresh_token == "refresh-1"
    assert refresh.commands[0].audit_context is not None
    assert refresh.commands[0].audit_context.user_agent == "testclient"
    cookies = _set_cookies(response)
    _assert_refresh_cookie(cookies, value="refresh-2")
    _assert_csrf_cookie(cookies)
    assert cookies["workflowforge_csrf"]["value"] != "csrf-1"


def test_refresh_rate_limit_returns_429_before_cookie_lookup() -> None:
    app = _app()
    refresh = FakeRefreshSession(_token_pair("access-2", "refresh-2"))
    limiter = FakeAuthenticationRateLimiter(refresh_allowed=RateLimitDecision(False, 17))
    app.dependency_overrides[get_refresh_session] = lambda: refresh
    app.dependency_overrides[get_authentication_rate_limiter] = lambda: limiter

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf-1",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf-1"),
            },
        )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
    assert response.json()["error"]["code"] == "rate_limited"
    assert refresh.commands == []
    assert limiter.refresh_checks == ["testclient"]


def test_refresh_invalid_token_returns_401_and_clears_cookies() -> None:
    app = _app()
    app.dependency_overrides[get_refresh_session] = lambda: FakeRefreshSession(
        InvalidRefreshTokenError("Invalid")
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={
                "X-CSRF-Token": "csrf-1",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf-1"),
            },
        )

    assert response.status_code == 401
    cookies = _set_cookies(response)
    _assert_cleared_cookie(cookies, "workflowforge_refresh", httponly=True)
    _assert_cleared_cookie(cookies, "workflowforge_csrf", httponly=False)


def test_me_requires_bearer_and_returns_safe_principal() -> None:
    app = _app()
    verifier = FakeVerifyAccessToken(_claims())
    app.dependency_overrides[get_verify_access_token] = lambda: verifier

    with TestClient(app) as client:
        missing = client.get("/api/v1/auth/me")
        wrong_scheme = client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"})
        malformed = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer"})
        valid = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer access-1"})

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert wrong_scheme.status_code == 401
    assert wrong_scheme.headers["www-authenticate"] == "Bearer"
    assert malformed.status_code == 401
    assert malformed.headers["www-authenticate"] == "Bearer"
    assert valid.status_code == 200
    assert valid.json() == {
        "user_id": str(USER_ID),
        "session_id": str(SESSION_ID),
        "issued_at": "2026-01-02T03:04:05Z",
        "expires_at": "2026-01-02T03:19:05Z",
    }
    assert verifier.tokens == ["access-1"]


def test_me_maps_invalid_and_expired_bearer_tokens_to_401() -> None:
    app = _app()
    app.dependency_overrides[get_verify_access_token] = lambda: FakeVerifyAccessToken(
        InvalidAccessTokenError("Invalid")
    )

    with TestClient(app) as client:
        invalid = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad"})

    app.dependency_overrides[get_verify_access_token] = lambda: FakeVerifyAccessToken(
        ExpiredAccessTokenError("Expired")
    )
    with TestClient(app) as client:
        expired = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer old"})

    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"
    assert invalid.json()["error"]["code"] == "authentication_failed"
    assert expired.status_code == 401
    assert expired.headers["www-authenticate"] == "Bearer"
    assert expired.json()["error"]["code"] == "authentication_failed"


def test_logout_revokes_current_session_and_clears_cookies() -> None:
    app = _app()
    logout = FakeLogoutSession()
    app.dependency_overrides[get_current_principal] = lambda: _principal()
    app.dependency_overrides[get_logout_session] = lambda: logout

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/logout",
            headers={
                "X-CSRF-Token": "csrf-1",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf-1"),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"revoked": True}
    assert logout.commands[0].user_id == USER_ID
    assert logout.commands[0].session_id == SessionId(SESSION_ID)
    assert logout.commands[0].audit_context is not None
    assert logout.commands[0].audit_context.user_agent == "testclient"
    cookies = _set_cookies(response)
    _assert_cleared_cookie(cookies, "workflowforge_refresh", httponly=True)
    _assert_cleared_cookie(cookies, "workflowforge_csrf", httponly=False)


def test_logout_all_returns_revoked_count_and_clears_cookies() -> None:
    app = _app()
    logout_all = FakeLogoutAllSessions(3)
    app.dependency_overrides[get_current_principal] = lambda: _principal()
    app.dependency_overrides[get_logout_all_sessions] = lambda: logout_all

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/logout-all",
            headers={
                "X-CSRF-Token": "csrf-1",
                "Cookie": _auth_cookie_header(refresh="refresh-1", csrf="csrf-1"),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"revoked_sessions": 3}
    assert logout_all.commands[0].user_id == USER_ID
    assert logout_all.commands[0].session_id == SessionId(SESSION_ID)
    assert logout_all.commands[0].audit_context is not None
    assert logout_all.commands[0].audit_context.user_agent == "testclient"
    cookies = _set_cookies(response)
    _assert_cleared_cookie(cookies, "workflowforge_refresh", httponly=True)
    _assert_cleared_cookie(cookies, "workflowforge_csrf", httponly=False)


class FakeStartUserSession:
    result: TokenPair | Exception
    commands: list[StartUserSessionCommand]

    def __init__(self, result: TokenPair | Exception) -> None:
        self.result = result
        self.commands = []

    async def __call__(self, command: StartUserSessionCommand) -> TokenPair:
        self.commands.append(command)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class NullAuditRecorder:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FailingAuditRecorder:
    async def record(self, event: AuditEvent) -> None:
        from workflowforge_application.audit import AuditPersistenceError

        raise AuditPersistenceError("audit failed")


class FakeAuthenticationRateLimiter(AuthenticationRateLimiter):
    def __init__(
        self,
        *,
        login_allowed: RateLimitDecision | None = None,
        refresh_allowed: RateLimitDecision | None = None,
        raise_on_login_failure: bool = False,
    ) -> None:
        self.login_allowed = login_allowed or RateLimitDecision(True)
        self.refresh_allowed = refresh_allowed or RateLimitDecision(True)
        self.raise_on_login_failure = raise_on_login_failure
        self.login_checks: list[tuple[str, str | None]] = []
        self.login_failures: list[tuple[str, str | None]] = []
        self.login_successes: list[tuple[str, str | None]] = []
        self.refresh_checks: list[str | None] = []
        self.refresh_failures: list[str | None] = []
        self.refresh_successes: list[str | None] = []

    async def check_login_allowed(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        self.login_checks.append((normalized_identifier, client_key))
        return self.login_allowed

    async def record_login_failure(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> RateLimitDecision:
        if self.raise_on_login_failure:
            raise RateLimitUnavailableError("down")
        self.login_failures.append((normalized_identifier, client_key))
        return self.login_allowed

    async def record_login_success(
        self,
        *,
        normalized_identifier: str,
        client_key: str | None,
    ) -> None:
        self.login_successes.append((normalized_identifier, client_key))

    async def check_refresh_allowed(self, *, client_key: str | None) -> RateLimitDecision:
        self.refresh_checks.append(client_key)
        return self.refresh_allowed

    async def record_refresh_failure(self, *, client_key: str | None) -> RateLimitDecision:
        self.refresh_failures.append(client_key)
        return self.refresh_allowed

    async def record_refresh_success(self, *, client_key: str | None) -> None:
        self.refresh_successes.append(client_key)


class FakeRefreshSession:
    def __init__(self, result: TokenPair | Exception) -> None:
        self.result = result
        self.commands: list[RefreshSessionCommand] = []

    async def __call__(self, command: RefreshSessionCommand) -> TokenPair:
        self.commands.append(command)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeVerifyAccessToken:
    def __init__(self, claims: AccessTokenClaims | Exception) -> None:
        self.claims = claims
        self.tokens: list[str] = []

    async def __call__(self, token: str) -> VerifiedAccessPrincipal:
        self.tokens.append(token)
        if isinstance(self.claims, Exception):
            raise self.claims
        return VerifiedAccessPrincipal(
            user_id=self.claims.user_id,
            session_id=self.claims.session_id,
            token_id=self.claims.token_id,
            issued_at=self.claims.issued_at,
            expires_at=self.claims.expires_at,
        )


class FakeLogoutSession:
    def __init__(self) -> None:
        self.commands: list[LogoutSessionCommand] = []

    async def __call__(self, command: LogoutSessionCommand) -> None:
        self.commands.append(command)


class FakeLogoutAllSessions:
    def __init__(self, revoked_sessions: int) -> None:
        self.revoked_sessions = revoked_sessions
        self.commands: list[LogoutAllSessionsCommand] = []

    async def __call__(self, command: LogoutAllSessionsCommand) -> LogoutAllSessionsResult:
        self.commands.append(command)
        return LogoutAllSessionsResult(revoked_sessions=self.revoked_sessions)


def _token_pair(access_token: str, refresh_token: str) -> TokenPair:
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        session_id=SessionId(SESSION_ID),
        access_token_expires_at=NOW + timedelta(minutes=15),
        refresh_token_expires_at=NOW + timedelta(days=30),
    )


def _app() -> Any:
    app = create_app(Settings(environment=Environment.TEST))
    app.dependency_overrides[get_independent_audit_recorder] = NullAuditRecorder
    app.dependency_overrides[get_authentication_rate_limiter] = FakeAuthenticationRateLimiter
    return app


def _claims() -> AccessTokenClaims:
    return AccessTokenClaims(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=TOKEN_ID,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _principal() -> VerifiedAccessPrincipal:
    claims = _claims()
    return VerifiedAccessPrincipal(
        user_id=claims.user_id,
        session_id=claims.session_id,
        token_id=claims.token_id,
        issued_at=claims.issued_at,
        expires_at=claims.expires_at,
    )


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

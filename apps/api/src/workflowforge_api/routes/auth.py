"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from starlette.responses import JSONResponse
from workflowforge_application.audit import AuditRecorder
from workflowforge_application.identity import (
    ExpiredRefreshTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LogoutAllSessions,
    LogoutAllSessionsCommand,
    LogoutSession,
    LogoutSessionCommand,
    RefreshRotationConflictError,
    RefreshSession,
    RefreshSessionCommand,
    RefreshTokenReplayError,
    SessionNotFoundError,
    SessionOwnershipError,
    StartUserSession,
    StartUserSessionCommand,
    TokenIssuanceError,
    TokenPair,
    UserAuthenticationDisabledError,
    VerifiedAccessPrincipal,
)
from workflowforge_domain.audit import AuditEventType, AuditOutcome
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.identity import Uuid4Generator

from workflowforge_api.audit import audit_request_context, record_independent_audit_event
from workflowforge_api.dependencies import (
    get_current_principal,
    get_independent_audit_recorder,
    get_logout_all_sessions,
    get_logout_session,
    get_refresh_session,
    get_settings,
    get_start_user_session,
)
from workflowforge_api.exception_handlers import ApiError
from workflowforge_api.middleware import current_correlation_id
from workflowforge_api.schemas.auth import (
    LoginRequest,
    LogoutAllResponse,
    LogoutResponse,
    MeResponse,
    TokenResponse,
)
from workflowforge_api.schemas.errors import ErrorDetail, ErrorResponse
from workflowforge_api.security import (
    CsrfTokenGenerator,
    CsrfValidationError,
    clear_auth_cookies,
    set_csrf_cookie,
    set_refresh_cookie,
    validate_csrf,
    validate_origin,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    start_user_session: Annotated[StartUserSession, Depends(get_start_user_session)],
    audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
) -> TokenResponse:
    """Authenticate with email/password and set refresh cookies."""

    _require_trusted_origin_if_present(request, settings)
    try:
        token_pair = await start_user_session(
            StartUserSessionCommand(
                email=payload.email,
                password=payload.password.get_secret_value(),
                audit_context=audit_request_context(request),
            )
        )
    except (InvalidCredentialsError, UserAuthenticationDisabledError) as exc:
        reason = (
            "disabled_user"
            if isinstance(exc, UserAuthenticationDisabledError)
            else "invalid_credentials"
        )
        await record_independent_audit_event(
            audit=audit,
            event_id=Uuid4Generator().new_uuid(),
            event_type=AuditEventType.AUTHENTICATION_LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            request_context=audit_request_context(request),
            metadata={"reason": reason},
        )
        raise _authentication_error() from exc
    except TokenIssuanceError as exc:
        raise _internal_auth_error() from exc

    csrf_token = CsrfTokenGenerator().generate()
    _set_auth_cookies(response, settings, token_pair.refresh_token, csrf_token)
    return _token_response(token_pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_session: Annotated[RefreshSession, Depends(get_refresh_session)],
    audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
) -> TokenResponse | JSONResponse:
    """Rotate the refresh token from the HttpOnly cookie."""

    _require_csrf(request, settings)
    refresh_token = request.cookies.get(settings.auth.refresh_cookie_name)
    if refresh_token is None:
        await _record_refresh_failure(request=request, audit=audit, reason="missing_cookie")
        raise _authentication_error()

    try:
        token_pair = await refresh_session(
            RefreshSessionCommand(
                refresh_token=refresh_token,
                audit_context=audit_request_context(request),
            )
        )
    except (
        InvalidRefreshTokenError,
        ExpiredRefreshTokenError,
        RefreshRotationConflictError,
    ) as exc:
        await _record_refresh_failure(request=request, audit=audit, reason=type(exc).__name__)
        return _auth_failure_with_cleared_cookies(settings)
    except RefreshTokenReplayError:
        return _auth_failure_with_cleared_cookies(settings)
    except TokenIssuanceError as exc:
        raise _internal_auth_error() from exc

    csrf_token = CsrfTokenGenerator().generate()
    _set_auth_cookies(response, settings, token_pair.refresh_token, csrf_token)
    return _token_response(token_pair)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[VerifiedAccessPrincipal, Depends(get_current_principal)],
    logout_session: Annotated[LogoutSession, Depends(get_logout_session)],
) -> LogoutResponse:
    """Revoke the current session and clear auth cookies."""

    _require_csrf(request, settings)
    try:
        await logout_session(
            LogoutSessionCommand(
                user_id=principal.user_id,
                session_id=principal.session_id,
                audit_context=audit_request_context(request),
            )
        )
    except SessionOwnershipError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="permission_denied",
            message="The request is not allowed.",
        ) from exc
    except SessionNotFoundError as exc:
        raise _authentication_error() from exc
    clear_auth_cookies(response, settings.auth)
    return LogoutResponse()


@router.post("/logout-all", response_model=LogoutAllResponse)
async def logout_all(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[VerifiedAccessPrincipal, Depends(get_current_principal)],
    logout_all_sessions: Annotated[LogoutAllSessions, Depends(get_logout_all_sessions)],
) -> LogoutAllResponse:
    """Revoke all sessions for the authenticated user and clear local cookies."""

    _require_csrf(request, settings)
    result = await logout_all_sessions(
        LogoutAllSessionsCommand(
            user_id=principal.user_id,
            session_id=principal.session_id,
            audit_context=audit_request_context(request),
        )
    )
    clear_auth_cookies(response, settings.auth)
    return LogoutAllResponse(revoked_sessions=result.revoked_sessions)


@router.get("/me", response_model=MeResponse)
async def me(
    principal: Annotated[VerifiedAccessPrincipal, Depends(get_current_principal)],
) -> MeResponse:
    """Return the current authenticated principal."""

    return MeResponse(
        user_id=principal.user_id,
        session_id=principal.session_id.value,
        issued_at=principal.issued_at,
        expires_at=principal.expires_at,
    )


def _require_csrf(request: Request, settings: Settings) -> None:
    try:
        _require_trusted_origin_if_present(request, settings)
        validate_csrf(request, settings.auth)
    except CsrfValidationError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="csrf_failed",
            message="CSRF validation failed.",
        ) from exc


def _require_trusted_origin_if_present(request: Request, settings: Settings) -> None:
    try:
        validate_origin(request, settings)
    except CsrfValidationError as exc:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="csrf_failed",
            message="CSRF validation failed.",
        ) from exc


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    refresh_token: str,
    csrf_token: str,
) -> None:
    max_age = settings.auth.refresh_token_lifetime_seconds
    set_refresh_cookie(response, settings.auth, refresh_token, max_age=max_age)
    set_csrf_cookie(response, settings.auth, csrf_token, max_age=max_age)


def _token_response(token_pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=token_pair.access_token,
        token_type=token_pair.token_type,
        access_token_expires_at=token_pair.access_token_expires_at,
        session_id=token_pair.session_id.value,
    )


def _authentication_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="authentication_failed",
        message="Authentication failed.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _internal_auth_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def _auth_failure_with_cleared_cookies(
    settings: Settings,
) -> JSONResponse:
    content = ErrorResponse(
        error=ErrorDetail(
            code="authentication_failed",
            message="Authentication failed.",
            correlation_id=current_correlation_id(),
        )
    ).model_dump()
    cleared = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=content,
        headers={"WWW-Authenticate": "Bearer"},
    )
    clear_auth_cookies(cleared, settings.auth)
    return cleared


async def _record_refresh_failure(
    *,
    request: Request,
    audit: AuditRecorder,
    reason: str,
) -> None:
    await record_independent_audit_event(
        audit=audit,
        event_id=Uuid4Generator().new_uuid(),
        event_type=AuditEventType.SESSION_REFRESH_FAILED,
        outcome=AuditOutcome.FAILURE,
        request_context=audit_request_context(request),
        metadata={"reason": reason},
    )

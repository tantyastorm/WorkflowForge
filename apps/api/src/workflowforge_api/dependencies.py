"""Typed accessors for API application state."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State
from workflowforge_application.authorization import (
    AuthorizationPolicy,
    PermissionDenied,
    ResolveTenantContext,
    ResolveTenantContextCommand,
    TenantAccessDenied,
    TenantContext,
    TenantMembershipInactive,
)
from workflowforge_application.health import DependencyHealthService
from workflowforge_application.identity import (
    AuthenticateUser,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    LogoutAllSessions,
    LogoutSession,
    RefreshSession,
    SessionLifecyclePolicy,
    StartUserSession,
    VerifiedAccessPrincipal,
    VerifyAccessToken,
)
from workflowforge_domain.identity import Permission
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.database import (
    SqlAlchemyTransactionManager,
    async_session_scope,
    create_async_session_factory,
)
from workflowforge_infrastructure.identity import (
    Argon2PasswordHasher,
    JwtAccessTokenCodec,
    SecretsRefreshTokenGenerator,
    Sha256RefreshTokenHasher,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    SystemClock,
    Uuid4Generator,
)

from workflowforge_api.exception_handlers import ApiError


@dataclass
class ReadinessState:
    """Per-application readiness marker."""

    ready: bool = False

    def mark_ready(self) -> None:
        """Mark this application instance as ready."""

        self.ready = True

    def mark_not_ready(self) -> None:
        """Mark this application instance as not ready."""

        self.ready = False


def set_readiness_state(state: State, readiness_state: ReadinessState) -> None:
    """Store readiness state on the application state container."""

    state.readiness = readiness_state


def get_readiness_state(request: Request) -> ReadinessState:
    """Return readiness state for the current application instance."""

    return cast("ReadinessState", request.app.state.readiness)


def set_dependency_health_service(
    state: State,
    service: DependencyHealthService,
) -> None:
    """Store dependency health service on the application state container."""

    state.dependency_health_service = service


def get_dependency_health_service(request: Request) -> DependencyHealthService:
    """Return the dependency health service for the current application instance."""

    return cast("DependencyHealthService", request.app.state.dependency_health_service)


bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    """Return configured process settings."""

    return cast("Settings", request.app.state.settings)


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one request-scoped SQLAlchemy session."""

    session_factory = create_async_session_factory(request.app.state.database_engine)
    async with async_session_scope(session_factory) as session:
        yield session


def _session_policy(settings: Settings) -> SessionLifecyclePolicy:
    return SessionLifecyclePolicy(
        access_token_lifetime=timedelta(seconds=settings.auth.access_token_lifetime_seconds),
        refresh_token_lifetime=timedelta(seconds=settings.auth.refresh_token_lifetime_seconds),
        session_lifetime=timedelta(seconds=settings.auth.session_lifetime_seconds),
    )


def get_start_user_session(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> StartUserSession:
    """Compose the login use case."""

    users = SqlAlchemyUserRepository(session)
    credentials = SqlAlchemyPasswordCredentialRepository(session)
    return StartUserSession(
        authenticate_user=AuthenticateUser(
            users=users,
            credentials=credentials,
            password_hasher=Argon2PasswordHasher(),
        ),
        sessions=SqlAlchemySessionRepository(session),
        access_tokens=JwtAccessTokenCodec(settings.auth),
        refresh_tokens=SecretsRefreshTokenGenerator.from_settings(settings.auth),
        refresh_token_hasher=Sha256RefreshTokenHasher(),
        transaction=SqlAlchemyTransactionManager(session),
        clock=SystemClock(),
        ids=Uuid4Generator(),
        policy=_session_policy(settings),
    )


def get_refresh_session(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> RefreshSession:
    """Compose the refresh use case."""

    return RefreshSession(
        sessions=SqlAlchemySessionRepository(session),
        access_tokens=JwtAccessTokenCodec(settings.auth),
        refresh_tokens=SecretsRefreshTokenGenerator.from_settings(settings.auth),
        refresh_token_hasher=Sha256RefreshTokenHasher(),
        transaction=SqlAlchemyTransactionManager(session),
        clock=SystemClock(),
        ids=Uuid4Generator(),
        policy=_session_policy(settings),
    )


def get_logout_session(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> LogoutSession:
    """Compose the single-session logout use case."""

    return LogoutSession(
        sessions=SqlAlchemySessionRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        clock=SystemClock(),
    )


def get_logout_all_sessions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> LogoutAllSessions:
    """Compose the logout-all use case."""

    return LogoutAllSessions(
        sessions=SqlAlchemySessionRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        clock=SystemClock(),
    )


def get_verify_access_token(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> VerifyAccessToken:
    """Compose the access-token verification use case."""

    return VerifyAccessToken(
        sessions=SqlAlchemySessionRepository(session),
        access_tokens=JwtAccessTokenCodec(settings.auth),
        clock=SystemClock(),
    )


def get_resolve_tenant_context(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ResolveTenantContext:
    """Compose the tenant-context resolver."""

    return ResolveTenantContext(
        organizations=SqlAlchemyOrganizationRepository(session),
        memberships=SqlAlchemyMembershipRepository(session),
    )


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verify_access_token: Annotated[VerifyAccessToken, Depends(get_verify_access_token)],
) -> VerifiedAccessPrincipal:
    """Return the current authenticated bearer principal."""

    if credentials is None:
        raise _authentication_error()
    if credentials.scheme.casefold() != "bearer" or not credentials.credentials:
        raise _authentication_error()
    try:
        return await verify_access_token(credentials.credentials)
    except (ExpiredAccessTokenError, InvalidAccessTokenError) as exc:
        raise _authentication_error() from exc


async def get_current_tenant_context(
    organization_id: Annotated[
        UUID,
        Path(
            description="Selected organization identifier for tenant-scoped requests.",
        ),
    ],
    principal: Annotated[VerifiedAccessPrincipal, Depends(get_current_principal)],
    resolve_tenant_context: Annotated[
        ResolveTenantContext,
        Depends(get_resolve_tenant_context),
    ],
) -> TenantContext:
    """Resolve the current authenticated user into the selected organization."""

    try:
        return await resolve_tenant_context(
            ResolveTenantContextCommand(
                user_id=principal.user_id,
                organization_id=organization_id,
            )
        )
    except (TenantAccessDenied, TenantMembershipInactive) as exc:
        raise _tenant_access_error() from exc


def require_permission(
    permission: Permission,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """Create a dependency requiring one typed permission."""

    _validate_permissions((permission,))

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require(context, permission)
        except PermissionDenied as exc:
            raise _permission_denied_error() from exc
        return context

    return dependency


def require_any_permission(
    *permissions: Permission,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """Create a dependency requiring at least one typed permission."""

    _validate_permissions(permissions)

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require_any(context, permissions)
        except PermissionDenied as exc:
            raise _permission_denied_error() from exc
        return context

    return dependency


def require_all_permissions(
    *permissions: Permission,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """Create a dependency requiring every typed permission."""

    _validate_permissions(permissions)

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require_all(context, permissions)
        except PermissionDenied as exc:
            raise _permission_denied_error() from exc
        return context

    return dependency


def _authentication_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="authentication_failed",
        message="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _tenant_access_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code="tenant_access_denied",
        message="The selected organization is not available.",
    )


def _permission_denied_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code="permission_denied",
        message="The request is not allowed.",
    )


def _validate_permissions(permissions: tuple[Permission, ...]) -> None:
    if not permissions:
        msg = "At least one permission is required."
        raise ValueError(msg)
    if any(not isinstance(permission, Permission) for permission in permissions):
        msg = "Permission dependencies require Permission values."
        raise TypeError(msg)

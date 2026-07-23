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
from workflowforge_application.audit import AuditRecorder
from workflowforge_application.authorization import (
    AuthorizationPolicy,
    PermissionDenied,
    ResolveTenantContext,
    ResolveTenantContextCommand,
    TenantAccessDenied,
    TenantContext,
    TenantMembershipInactive,
)
from workflowforge_application.batches import BatchService
from workflowforge_application.cases import CaseService
from workflowforge_application.documents import DocumentService, ObjectStorage, UploadDocument
from workflowforge_application.health import DependencyHealthService
from workflowforge_application.identity import (
    AuthenticateUser,
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    ListUserOrganizations,
    LogoutAllSessions,
    LogoutSession,
    RefreshSession,
    SessionLifecyclePolicy,
    StartUserSession,
    VerifiedAccessPrincipal,
    VerifyAccessToken,
)
from workflowforge_application.security import AuthenticationRateLimiter
from workflowforge_domain.audit import AuditEventType, AuditOutcome
from workflowforge_domain.identity import Permission
from workflowforge_infrastructure.audit import SqlAlchemyAuditRepository
from workflowforge_infrastructure.batches import SqlAlchemyBatchRepository
from workflowforge_infrastructure.cases import SqlAlchemyCaseRepository
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.database import (
    SqlAlchemyTransactionManager,
    async_session_scope,
    create_async_session_factory,
)
from workflowforge_infrastructure.documents import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyUploadIdempotencyRepository,
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
from workflowforge_infrastructure.security import RedisAuthenticationRateLimiter
from workflowforge_infrastructure.storage import S3ObjectStorage

from workflowforge_api.audit import (
    IndependentSqlAlchemyAuditRecorder,
    audit_request_context,
    record_independent_audit_event,
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
        audit=SqlAlchemyAuditRepository(session),
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
        audit=SqlAlchemyAuditRepository(session),
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
        ids=Uuid4Generator(),
        audit=SqlAlchemyAuditRepository(session),
    )


def get_logout_all_sessions(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> LogoutAllSessions:
    """Compose the logout-all use case."""

    return LogoutAllSessions(
        sessions=SqlAlchemySessionRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        clock=SystemClock(),
        ids=Uuid4Generator(),
        audit=SqlAlchemyAuditRepository(session),
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


def get_list_user_organizations(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> ListUserOrganizations:
    """Compose the current-user organization listing query."""

    return ListUserOrganizations(
        organizations=SqlAlchemyOrganizationRepository(session),
        memberships=SqlAlchemyMembershipRepository(session),
    )


def get_independent_audit_recorder(request: Request) -> AuditRecorder:
    """Return an audit recorder that commits independently of request state."""

    return IndependentSqlAlchemyAuditRecorder(request.app.state.database_engine)


def get_authentication_rate_limiter(request: Request) -> AuthenticationRateLimiter:
    """Return the Redis-backed authentication rate limiter."""

    return RedisAuthenticationRateLimiter(
        request.app.state.redis_client,
        get_settings(request).rate_limit,
    )


def get_upload_document(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    request: Request,
) -> UploadDocument:
    """Compose the document upload use case."""

    return UploadDocument(
        documents=SqlAlchemyDocumentRepository(session),
        idempotency=SqlAlchemyUploadIdempotencyRepository(session),
        storage=S3ObjectStorage(request.app.state.s3_client, settings.s3),
        transaction=SqlAlchemyTransactionManager(session),
        audit=SqlAlchemyAuditRepository(session),
        ids=Uuid4Generator(),
        max_bytes=settings.document_upload.max_bytes,
        idempotency_ttl=timedelta(seconds=settings.document_upload.idempotency_ttl_seconds),
    )


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> DocumentService:
    """Compose the document metadata service."""

    return DocumentService(
        SqlAlchemyDocumentRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        audit=SqlAlchemyAuditRepository(session),
        ids=Uuid4Generator(),
    )


def get_object_storage(
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> ObjectStorage:
    """Return object storage adapter for API use cases."""

    return S3ObjectStorage(request.app.state.s3_client, settings.s3)


def get_batch_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> BatchService:
    """Compose the batch application service."""

    return BatchService(
        SqlAlchemyBatchRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        audit=SqlAlchemyAuditRepository(session),
        ids=Uuid4Generator(),
    )


def get_case_service(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CaseService:
    """Compose the case application service."""

    return CaseService(
        SqlAlchemyCaseRepository(session),
        transaction=SqlAlchemyTransactionManager(session),
        audit=SqlAlchemyAuditRepository(session),
        ids=Uuid4Generator(),
    )


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verify_access_token: Annotated[VerifyAccessToken, Depends(get_verify_access_token)],
    request: Request,
    audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
) -> VerifiedAccessPrincipal:
    """Return the current authenticated bearer principal."""

    if credentials is None:
        await _record_access_token_rejected(request=request, audit=audit)
        raise _authentication_error()
    if credentials.scheme.casefold() != "bearer" or not credentials.credentials:
        await _record_access_token_rejected(request=request, audit=audit)
        raise _authentication_error()
    try:
        return await verify_access_token(credentials.credentials)
    except (ExpiredAccessTokenError, InvalidAccessTokenError) as exc:
        await _record_access_token_rejected(request=request, audit=audit)
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
    request: Request,
    audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
) -> TenantContext:
    """Resolve the current authenticated user into the selected organization."""

    try:
        return await resolve_tenant_context(
            ResolveTenantContextCommand(
                user_id=principal.user_id,
                organization_id=organization_id,
            )
        )
    except TenantMembershipInactive as exc:
        await record_independent_audit_event(
            audit=audit,
            event_id=Uuid4Generator().new_uuid(),
            event_type=AuditEventType.TENANCY_INACTIVE_MEMBERSHIP,
            outcome=AuditOutcome.DENIED,
            actor_user_id=exc.user_id,
            organization_id=exc.organization_id,
            session_id=principal.session_id.value,
            request_context=audit_request_context(request),
            metadata={"membership_status": exc.status.value},
        )
        raise _tenant_access_error() from exc
    except TenantAccessDenied as exc:
        event_type = (
            AuditEventType.TENANCY_INACTIVE_ORGANIZATION
            if exc.reason == "organization inactive"
            else AuditEventType.TENANCY_ACCESS_DENIED
        )
        await record_independent_audit_event(
            audit=audit,
            event_id=Uuid4Generator().new_uuid(),
            event_type=event_type,
            outcome=AuditOutcome.DENIED,
            actor_user_id=exc.user_id,
            organization_id=exc.organization_id,
            session_id=principal.session_id.value,
            request_context=audit_request_context(request),
            metadata={"reason": exc.reason},
        )
        raise _tenant_access_error() from exc


def require_permission(
    permission: Permission,
) -> Callable[..., Awaitable[TenantContext]]:
    """Create a dependency requiring one typed permission."""

    _validate_permissions((permission,))

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
        request: Request,
        audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require(context, permission)
        except PermissionDenied as exc:
            await _record_permission_denied(request=request, audit=audit, exc=exc)
            raise _permission_denied_error() from exc
        return context

    return dependency


def require_any_permission(
    *permissions: Permission,
) -> Callable[..., Awaitable[TenantContext]]:
    """Create a dependency requiring at least one typed permission."""

    _validate_permissions(permissions)

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
        request: Request,
        audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require_any(context, permissions)
        except PermissionDenied as exc:
            await _record_permission_denied(request=request, audit=audit, exc=exc)
            raise _permission_denied_error() from exc
        return context

    return dependency


def require_all_permissions(
    *permissions: Permission,
) -> Callable[..., Awaitable[TenantContext]]:
    """Create a dependency requiring every typed permission."""

    _validate_permissions(permissions)

    async def dependency(
        context: Annotated[TenantContext, Depends(get_current_tenant_context)],
        request: Request,
        audit: Annotated[AuditRecorder, Depends(get_independent_audit_recorder)],
    ) -> TenantContext:
        try:
            AuthorizationPolicy().require_all(context, permissions)
        except PermissionDenied as exc:
            await _record_permission_denied(request=request, audit=audit, exc=exc)
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


async def _record_access_token_rejected(
    *,
    request: Request,
    audit: AuditRecorder,
) -> None:
    await record_independent_audit_event(
        audit=audit,
        event_id=Uuid4Generator().new_uuid(),
        event_type=AuditEventType.AUTHENTICATION_ACCESS_TOKEN_REJECTED,
        outcome=AuditOutcome.FAILURE,
        request_context=audit_request_context(request),
    )


async def _record_permission_denied(
    *,
    request: Request,
    audit: AuditRecorder,
    exc: PermissionDenied,
) -> None:
    await record_independent_audit_event(
        audit=audit,
        event_id=Uuid4Generator().new_uuid(),
        event_type=AuditEventType.AUTHORIZATION_PERMISSION_DENIED,
        outcome=AuditOutcome.DENIED,
        actor_user_id=exc.user_id,
        organization_id=exc.organization_id,
        request_context=audit_request_context(request),
        metadata={"permission": exc.permission.value},
    )

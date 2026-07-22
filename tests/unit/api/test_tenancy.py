"""Tenant context API dependency tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from workflowforge_api.dependencies import (
    get_current_principal,
    get_resolve_tenant_context,
    require_all_permissions,
    require_any_permission,
    require_permission,
)
from workflowforge_api.factory import create_app
from workflowforge_application.authorization import (
    ResolveTenantContextCommand,
    TenantAccessDenied,
    TenantContext,
    TenantMembershipInactive,
)
from workflowforge_application.identity import VerifiedAccessPrincipal
from workflowforge_domain.identity import MembershipStatus, Permission, Role, SessionId
from workflowforge_infrastructure.config import Environment, Settings

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("77777777-7777-4777-8777-777777777777")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_ORG_ID = UUID("22222222-2222-4222-8222-333333333333")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")


def test_tenant_context_route_returns_safe_context_for_active_membership() -> None:
    app = _app_with_context(_context(role=Role.ADMIN))

    with TestClient(app) as client:
        response = client.get(f"/api/v1/organizations/{ORG_ID}/tenancy/context")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(USER_ID)
    assert body["organization_id"] == str(ORG_ID)
    assert body["membership_id"] == str(MEMBERSHIP_ID)
    assert body["role"] == "admin"
    assert "membership.update" in body["permissions"]
    assert "access_token" not in body


def test_tenant_context_requires_valid_bearer_before_resolution() -> None:
    app = create_app(Settings(environment=Environment.TEST))
    resolver = FakeResolveTenantContext(_context())
    app.dependency_overrides[get_resolve_tenant_context] = lambda: resolver

    with TestClient(app) as client:
        response = client.get(f"/api/v1/organizations/{ORG_ID}/tenancy/context")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "authentication_failed"
    assert resolver.commands == []


def test_tenant_context_rejects_malformed_organization_id() -> None:
    app = _app_with_context(_context())

    with TestClient(app) as client:
        response = client.get("/api/v1/organizations/not-a-uuid/tenancy/context")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_tenant_context_maps_missing_and_inactive_membership_to_generic_403() -> None:
    for denial in (
        TenantAccessDenied(
            user_id=USER_ID,
            organization_id=ORG_ID,
            reason="membership not found",
        ),
        TenantMembershipInactive(
            user_id=USER_ID,
            organization_id=ORG_ID,
            membership_id=MEMBERSHIP_ID,
            status=MembershipStatus.SUSPENDED,
        ),
    ):
        app = _app_with_context(denial)

        with TestClient(app) as client:
            response = client.get(f"/api/v1/organizations/{ORG_ID}/tenancy/context")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "tenant_access_denied"
        assert response.json()["error"]["message"] == "The selected organization is not available."


def test_permission_probe_allows_owner_and_denies_role_without_permission() -> None:
    owner_app = _app_with_context(_context(role=Role.OWNER))
    operator_app = _app_with_context(_context(role=Role.OPERATOR))

    with TestClient(owner_app) as client:
        allowed = client.get(
            f"/api/v1/organizations/{ORG_ID}/tenancy/authorized-probe",
            params={"role": "owner"},
        )
    with TestClient(operator_app) as client:
        denied = client.get(f"/api/v1/organizations/{ORG_ID}/tenancy/authorized-probe")

    assert allowed.status_code == 200
    assert allowed.json() == {"authorized": True, "organization_id": str(ORG_ID)}
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"


def test_permission_factories_reject_empty_or_untyped_configuration() -> None:
    with pytest.raises(ValueError):
        require_any_permission()

    with pytest.raises(ValueError):
        require_all_permissions()

    with pytest.raises(TypeError):
        require_permission("organization.read")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        require_any_permission(Permission.ORGANIZATION_READ, "audit.read")  # type: ignore[arg-type]


def test_multiple_permission_dependencies_reuse_cached_tenant_context() -> None:
    resolver = FakeResolveTenantContext(_context(role=Role.OWNER))
    app = _app_with_resolver(resolver)

    @app.get("/api/v1/organizations/{organization_id}/tenancy/cache-probe")
    async def cache_probe(
        _read_context: Annotated[
            TenantContext,
            Depends(require_permission(Permission.ORGANIZATION_READ)),
        ],
        _security_context: Annotated[
            TenantContext,
            Depends(require_all_permissions(Permission.SECURITY_MANAGE)),
        ],
    ) -> dict[str, bool]:
        return {"authorized": True}

    with TestClient(app) as client:
        response = client.get(f"/api/v1/organizations/{ORG_ID}/tenancy/cache-probe")

    assert response.status_code == 200
    assert response.json() == {"authorized": True}
    assert resolver.commands == [
        ResolveTenantContextCommand(user_id=USER_ID, organization_id=ORG_ID)
    ]


def test_tenant_context_uses_selected_path_organization_only() -> None:
    context = _context(role=Role.AUDITOR, organization_id=OTHER_ORG_ID)
    resolver = FakeResolveTenantContext(context)
    app = _app_with_resolver(resolver)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/organizations/{OTHER_ORG_ID}/tenancy/context")

    assert response.status_code == 200
    assert resolver.commands == [
        ResolveTenantContextCommand(user_id=USER_ID, organization_id=OTHER_ORG_ID)
    ]
    assert response.json()["organization_id"] == str(OTHER_ORG_ID)
    assert "audit.read" in response.json()["permissions"]


def _app_with_context(result: TenantContext | Exception) -> FastAPI:
    return _app_with_resolver(FakeResolveTenantContext(result))


def _app_with_resolver(resolver: FakeResolveTenantContext) -> FastAPI:
    app = create_app(Settings(environment=Environment.TEST))
    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_resolve_tenant_context] = lambda: resolver
    return app


def _principal() -> VerifiedAccessPrincipal:
    return VerifiedAccessPrincipal(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=TOKEN_ID,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _context(
    *,
    role: Role = Role.ADMIN,
    organization_id: UUID = ORG_ID,
) -> TenantContext:
    return TenantContext.create(
        user_id=USER_ID,
        organization_id=organization_id,
        membership_id=MEMBERSHIP_ID,
        role=role,
    )


class FakeResolveTenantContext:
    def __init__(self, result: TenantContext | Exception) -> None:
        self._result = result
        self.commands: list[ResolveTenantContextCommand] = []

    async def __call__(self, command: ResolveTenantContextCommand) -> TenantContext:
        self.commands.append(command)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

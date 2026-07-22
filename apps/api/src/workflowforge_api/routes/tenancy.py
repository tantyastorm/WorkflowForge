"""Tenant context and authorization probe routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from workflowforge_application.authorization import TenantContext
from workflowforge_domain.identity import Permission

from workflowforge_api.dependencies import get_current_tenant_context, require_permission
from workflowforge_api.schemas.tenancy import (
    AuthorizedProbeResponse,
    TenantContextResponse,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/tenancy",
    tags=["tenancy"],
)


@router.get(
    "/context",
    response_model=TenantContextResponse,
    summary="Resolve tenant context system probe",
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "The selected organization is not available."},
        422: {"description": "The organization identifier is invalid."},
    },
)
async def context(
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant_context)],
) -> TenantContextResponse:
    """Return the resolved tenant context for authenticated system probes."""

    return TenantContextResponse(
        user_id=tenant_context.user_id,
        organization_id=tenant_context.organization_id,
        membership_id=tenant_context.membership_id,
        role=tenant_context.role,
        permissions=tuple(sorted(tenant_context.permissions, key=lambda item: item.value)),
    )


@router.get(
    "/authorized-probe",
    response_model=AuthorizedProbeResponse,
    summary="Permission-protected tenant system probe",
    responses={
        401: {"description": "Authentication is required."},
        403: {"description": "Tenant access or permission is denied."},
        422: {"description": "The organization identifier is invalid."},
    },
)
async def authorized_probe(
    tenant_context: Annotated[
        TenantContext,
        Depends(require_permission(Permission.SECURITY_MANAGE)),
    ],
) -> AuthorizedProbeResponse:
    """Return success when the selected tenant context has security management permission."""

    return AuthorizedProbeResponse(
        authorized=True,
        organization_id=tenant_context.organization_id,
    )

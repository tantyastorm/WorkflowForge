"""Tenant context probe HTTP schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from workflowforge_domain.identity import Permission, Role


class TenantContextResponse(BaseModel):
    """Safe tenant context response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    role: Role
    permissions: tuple[Permission, ...]


class AuthorizedProbeResponse(BaseModel):
    """Permission-protected system probe response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    authorized: bool
    organization_id: UUID

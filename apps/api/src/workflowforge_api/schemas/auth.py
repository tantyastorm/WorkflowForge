"""Authentication HTTP schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from workflowforge_domain.identity import MembershipStatus, Role


class LoginRequest(BaseModel):
    """Email/password login request."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1, json_schema_extra={"writeOnly": True})


class TokenResponse(BaseModel):
    """Access-token response with safe session metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    token_type: str
    access_token_expires_at: datetime
    session_id: UUID


class MeResponse(BaseModel):
    """Current authenticated principal response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    session_id: UUID
    issued_at: datetime
    expires_at: datetime


class AuthOrganizationResponse(BaseModel):
    """Current user's safe organization selection item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    name: str
    slug: str
    membership_id: UUID
    membership_role: Role
    membership_status: MembershipStatus


class LogoutResponse(BaseModel):
    """Stable logout response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revoked: bool = True


class LogoutAllResponse(BaseModel):
    """Logout-all response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revoked_sessions: int

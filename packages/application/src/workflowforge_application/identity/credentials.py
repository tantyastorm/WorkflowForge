"""Password credential application contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from workflowforge_domain.identity.entities import validate_uuid
from workflowforge_domain.identity.errors import InvalidIdentifier, InvalidTimestamp


@dataclass(frozen=True, slots=True)
class PasswordCredential:
    """Durable password credential state exposed only through credential ports."""

    user_id: UUID
    password_hash: str = field(repr=False)
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        validate_uuid(self.user_id, field_name="Password credential user identifier")
        if not self.password_hash:
            msg = "Password credential hash must not be empty."
            raise InvalidIdentifier(msg)
        created_at = _normalize_timestamp(self.created_at, field_name="created_at")
        updated_at = _normalize_timestamp(self.updated_at, field_name="updated_at")
        if updated_at < created_at:
            msg = (
                "Password credential updated timestamp must not be earlier than creation timestamp."
            )
            raise InvalidTimestamp(msg)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)

    def replace_hash(self, password_hash: str, *, now: datetime) -> PasswordCredential:
        """Return this credential with a replacement hash."""

        updated_at = _normalize_timestamp(now, field_name="now")
        if updated_at < self.created_at:
            msg = (
                "Password credential mutation timestamp must not be earlier "
                "than creation timestamp."
            )
            raise InvalidTimestamp(msg)
        return PasswordCredential(
            user_id=self.user_id,
            password_hash=password_hash,
            created_at=self.created_at,
            updated_at=updated_at,
        )


def _normalize_timestamp(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} timestamp must be timezone-aware."
        raise InvalidTimestamp(msg)
    return value.astimezone(UTC)

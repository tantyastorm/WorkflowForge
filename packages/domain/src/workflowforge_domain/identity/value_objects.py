"""Identity and tenancy value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from workflowforge_domain.identity.errors import (
    InvalidEmailAddress,
    InvalidOrganizationSlug,
)

EMAIL_MIN_LENGTH = 3
EMAIL_MAX_LENGTH = 254
ORGANIZATION_SLUG_MIN_LENGTH = 3
ORGANIZATION_SLUG_MAX_LENGTH = 63

_ORGANIZATION_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """Email address whose identity is its normalized value.

    Normalization is exactly ``email.strip().casefold()``. Provider-specific
    transformations such as Gmail dot removal and plus-tag stripping are not
    applied.
    """

    display: str
    normalized: str = field(init=False, compare=False)

    def __post_init__(self) -> None:
        display = self.display.strip()
        normalized = display.casefold()

        if not normalized:
            msg = "Email address must not be empty."
            raise InvalidEmailAddress(msg)
        if len(normalized) < EMAIL_MIN_LENGTH:
            msg = f"Email address must be at least {EMAIL_MIN_LENGTH} characters."
            raise InvalidEmailAddress(msg)
        if len(normalized) > EMAIL_MAX_LENGTH:
            msg = f"Email address must be at most {EMAIL_MAX_LENGTH} characters."
            raise InvalidEmailAddress(msg)
        if any(character.isspace() for character in normalized):
            msg = "Email address must not contain whitespace."
            raise InvalidEmailAddress(msg)
        if normalized.count("@") != 1:
            msg = "Email address must contain exactly one @ separator."
            raise InvalidEmailAddress(msg)

        local_part, domain_part = normalized.split("@", maxsplit=1)
        if not local_part:
            msg = "Email address local part must not be empty."
            raise InvalidEmailAddress(msg)
        if not domain_part:
            msg = "Email address domain part must not be empty."
            raise InvalidEmailAddress(msg)
        if "." not in domain_part:
            msg = "Email address domain part must contain a dot."
            raise InvalidEmailAddress(msg)
        if domain_part.startswith(".") or domain_part.endswith(".") or ".." in domain_part:
            msg = "Email address domain part is invalid."
            raise InvalidEmailAddress(msg)

        object.__setattr__(self, "display", display)
        object.__setattr__(self, "normalized", normalized)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EmailAddress):
            return NotImplemented
        return self.normalized == other.normalized

    def __hash__(self) -> int:
        return hash(self.normalized)

    def __repr__(self) -> str:
        return f"EmailAddress(normalized={self.normalized!r})"

    def __str__(self) -> str:
        return self.display


@dataclass(frozen=True, slots=True)
class OrganizationSlug:
    """Stable lowercase organization slug.

    Uppercase input is normalized to lowercase. Construction is explicit; slugs
    are not generated from organization names.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()

        if len(normalized) < ORGANIZATION_SLUG_MIN_LENGTH:
            msg = f"Organization slug must be at least {ORGANIZATION_SLUG_MIN_LENGTH} characters."
            raise InvalidOrganizationSlug(msg)
        if len(normalized) > ORGANIZATION_SLUG_MAX_LENGTH:
            msg = f"Organization slug must be at most {ORGANIZATION_SLUG_MAX_LENGTH} characters."
            raise InvalidOrganizationSlug(msg)
        if not _ORGANIZATION_SLUG_PATTERN.fullmatch(normalized):
            msg = (
                "Organization slug must contain only lowercase letters, digits, "
                "and single hyphens between alphanumeric characters."
            )
            raise InvalidOrganizationSlug(msg)

        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value

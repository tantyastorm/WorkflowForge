"""Identity value object tests."""

from dataclasses import FrozenInstanceError

import pytest
from workflowforge_domain.identity import (
    EmailAddress,
    InvalidEmailAddress,
    InvalidOrganizationSlug,
    OrganizationSlug,
)
from workflowforge_domain.identity.value_objects import (
    EMAIL_MAX_LENGTH,
    ORGANIZATION_SLUG_MAX_LENGTH,
    ORGANIZATION_SLUG_MIN_LENGTH,
)


def test_email_trims_outer_whitespace_and_preserves_display_form() -> None:
    email = EmailAddress("  Person@Example.COM  ")

    assert str(email) == "Person@Example.COM"
    assert email.display == "Person@Example.COM"
    assert email.normalized == "person@example.com"


def test_email_equality_and_hashing_use_normalized_identity() -> None:
    left = EmailAddress("Person@Example.com")
    right = EmailAddress("person@example.COM")

    assert left == right
    assert hash(left) == hash(right)
    assert len({left, right}) == 1
    assert repr(left) == "EmailAddress(normalized='person@example.com')"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "example.com",
        "a@example.com@extra",
        "@example.com",
        "person@",
        "per son@example.com",
        "person@exa mple.com",
        "person@example",
        "person@.example.com",
        "person@example.com.",
        "person@example..com",
    ],
)
def test_invalid_email_addresses_are_rejected(value: str) -> None:
    with pytest.raises(InvalidEmailAddress):
        EmailAddress(value)


def test_email_length_boundaries_are_explicit() -> None:
    with pytest.raises(InvalidEmailAddress, match="at least"):
        EmailAddress("a@")

    assert EmailAddress("a@b.co").normalized == "a@b.co"

    too_long_local = "a" * (EMAIL_MAX_LENGTH - len("@example.com") + 1)
    with pytest.raises(InvalidEmailAddress, match="at most"):
        EmailAddress(f"{too_long_local}@example.com")


def test_email_does_not_apply_provider_specific_transformations() -> None:
    dotted = EmailAddress("first.last@gmail.com")
    undotted = EmailAddress("firstlast@gmail.com")
    plus_tagged = EmailAddress("first.last+tag@gmail.com")

    assert dotted != undotted
    assert dotted.normalized == "first.last@gmail.com"
    assert plus_tagged.normalized == "first.last+tag@gmail.com"


def test_organization_slug_accepts_valid_lowercase_numeric_and_hyphenated_values() -> None:
    slug = OrganizationSlug("team-42")

    assert slug.value == "team-42"
    assert str(slug) == "team-42"


def test_organization_slug_normalizes_uppercase_input() -> None:
    assert OrganizationSlug("Team-42").value == "team-42"


@pytest.mark.parametrize(
    "value",
    [
        "bad slug",
        "bad_slug",
        "bad.slug",
        "-bad",
        "bad-",
        "bad--slug",
    ],
)
def test_invalid_organization_slugs_are_rejected(value: str) -> None:
    with pytest.raises(InvalidOrganizationSlug):
        OrganizationSlug(value)


def test_organization_slug_length_boundaries_are_explicit() -> None:
    with pytest.raises(InvalidOrganizationSlug, match="at least"):
        OrganizationSlug("a" * (ORGANIZATION_SLUG_MIN_LENGTH - 1))

    assert OrganizationSlug("a" * ORGANIZATION_SLUG_MIN_LENGTH).value == (
        "a" * ORGANIZATION_SLUG_MIN_LENGTH
    )
    assert OrganizationSlug("a" * ORGANIZATION_SLUG_MAX_LENGTH).value == (
        "a" * ORGANIZATION_SLUG_MAX_LENGTH
    )

    with pytest.raises(InvalidOrganizationSlug, match="at most"):
        OrganizationSlug("a" * (ORGANIZATION_SLUG_MAX_LENGTH + 1))


def test_organization_slug_is_immutable() -> None:
    slug = OrganizationSlug("team-42")

    with pytest.raises(FrozenInstanceError):
        slug.value = "other"  # type: ignore[misc]

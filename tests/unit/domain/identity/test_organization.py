"""Organization entity tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_domain.identity import (
    InvalidOrganizationName,
    InvalidTimestamp,
    Organization,
    OrganizationSlug,
)
from workflowforge_domain.identity.entities import ORGANIZATION_NAME_MAX_LENGTH

ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC)


def test_organization_creation_normalizes_values_and_defaults_active() -> None:
    organization = _organization(name="  Workflow   Forge  ")

    assert organization.id == ORGANIZATION_ID
    assert organization.name == "Workflow Forge"
    assert organization.slug == OrganizationSlug("workflow-forge")
    assert organization.is_active is True
    assert organization.created_at == NOW
    assert organization.updated_at == NOW
    assert organization.deactivated_at is None


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_invalid_organization_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidOrganizationName):
        _organization(name=name)


def test_organization_name_length_boundaries_are_enforced() -> None:
    assert _organization(name="a" * ORGANIZATION_NAME_MAX_LENGTH).name == (
        "a" * ORGANIZATION_NAME_MAX_LENGTH
    )

    with pytest.raises(InvalidOrganizationName, match="at most"):
        _organization(name="a" * (ORGANIZATION_NAME_MAX_LENGTH + 1))


def test_organization_rename_does_not_change_slug_and_is_idempotent() -> None:
    organization = _organization()

    renamed = organization.rename("  New   Name  ", now=LATER)
    same = renamed.rename("New Name", now=LATER + timedelta(seconds=1))

    assert renamed.name == "New Name"
    assert renamed.slug == organization.slug
    assert renamed.updated_at == LATER
    assert same is renamed


def test_organization_deactivation_and_reactivation_are_idempotent() -> None:
    organization = _organization()

    deactivated = organization.deactivate(now=LATER)
    repeated_deactivation = deactivated.deactivate(now=LATER + timedelta(seconds=1))
    reactivated_at = LATER + timedelta(seconds=2)
    reactivated = deactivated.reactivate(now=reactivated_at)
    repeated_reactivation = reactivated.reactivate(now=reactivated_at + timedelta(seconds=1))

    assert deactivated.is_active is False
    assert deactivated.deactivated_at == LATER
    assert repeated_deactivation is deactivated
    assert reactivated.is_active is True
    assert reactivated.deactivated_at is None
    assert reactivated.updated_at == reactivated_at
    assert repeated_reactivation is reactivated


def test_organization_rejects_naive_and_contradictory_timestamps() -> None:
    with pytest.raises(InvalidTimestamp, match="timezone-aware"):
        _organization(now=datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(InvalidTimestamp, match="deactivated"):
        Organization(
            id=ORGANIZATION_ID,
            name="WorkflowForge",
            slug=OrganizationSlug("workflow-forge"),
            is_active=True,
            created_at=NOW,
            updated_at=NOW,
            deactivated_at=LATER,
        )

    with pytest.raises(InvalidTimestamp, match="Inactive"):
        Organization(
            id=ORGANIZATION_ID,
            name="WorkflowForge",
            slug=OrganizationSlug("workflow-forge"),
            is_active=False,
            created_at=NOW,
            updated_at=NOW,
            deactivated_at=None,
        )


def _organization(
    *,
    name: str = "WorkflowForge",
    slug: OrganizationSlug | None = None,
    now: datetime = NOW,
) -> Organization:
    return Organization.create(
        id=ORGANIZATION_ID,
        name=name,
        slug=slug or OrganizationSlug("workflow-forge"),
        now=now,
    )

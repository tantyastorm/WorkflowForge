"""Identity persistence mapping tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Table
from workflowforge_domain.identity import (
    EmailAddress,
    InvalidTimestamp,
    Membership,
    Organization,
    OrganizationSlug,
    Role,
    User,
)
from workflowforge_infrastructure.identity.models import (
    MembershipRecord,
    OrganizationRecord,
    UserRecord,
)
from workflowforge_infrastructure.identity.repository import (
    _membership_from_record,
    _organization_from_record,
    _record_from_membership,
    _record_from_organization,
    _record_from_user,
    _user_from_record,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_user_record_mapping_round_trips_domain_values() -> None:
    user = _user()

    record = _record_from_user(user)
    mapped = _user_from_record(record)

    assert isinstance(record, UserRecord)
    assert record.email == "Ada@Example.com"
    assert record.normalized_email == "ada@example.com"
    assert mapped == user


def test_organization_record_mapping_round_trips_domain_values() -> None:
    organization = _organization()

    record = _record_from_organization(organization)
    mapped = _organization_from_record(record)

    assert isinstance(record, OrganizationRecord)
    assert record.slug == "workflow-forge"
    assert mapped == organization


def test_membership_record_mapping_round_trips_domain_values_and_enums() -> None:
    membership = _membership()

    record = _record_from_membership(membership)
    mapped = _membership_from_record(record)

    assert isinstance(record, MembershipRecord)
    assert record.role == "owner"
    assert record.status == "active"
    assert mapped == membership


def test_identity_tables_define_expected_constraints_and_indexes() -> None:
    assert UserRecord.__table__.c.normalized_email.unique is True
    assert UserRecord.__table__.c.normalized_email.index is True
    assert OrganizationRecord.__table__.c.slug.unique is True
    assert OrganizationRecord.__table__.c.slug.index is True

    membership_table = cast(Table, MembershipRecord.__table__)
    unique_constraints = {
        constraint.name for constraint in membership_table.constraints if constraint.name
    }
    indexes = {index.name for index in membership_table.indexes}

    assert "uq_memberships_organization_user" in unique_constraints
    assert "ix_memberships_organization_id" in indexes
    assert "ix_memberships_user_id" in indexes
    assert "ix_memberships_organization_status" in indexes
    assert "ix_memberships_user_status" in indexes
    assert "ix_memberships_organization_user_status" in indexes


def test_invalid_database_user_state_fails_loudly() -> None:
    record = _record_from_user(_user().disable(now=NOW))
    record.is_active = True

    with pytest.raises(InvalidTimestamp, match="Active user"):
        _user_from_record(record)


def test_invalid_database_membership_state_fails_loudly() -> None:
    record = _record_from_membership(_membership())
    record.joined_at = None

    with pytest.raises(InvalidTimestamp, match="Active membership"):
        _membership_from_record(record)


def _user() -> User:
    return User.create(
        id=USER_ID,
        email=EmailAddress("Ada@Example.com"),
        display_name="Ada Lovelace",
        now=NOW,
    )


def _organization() -> Organization:
    return Organization.create(
        id=ORGANIZATION_ID,
        name="WorkflowForge",
        slug=OrganizationSlug("workflow-forge"),
        now=NOW,
    )


def _membership() -> Membership:
    return Membership.activate_directly(
        id=MEMBERSHIP_ID,
        user_id=USER_ID,
        organization_id=ORGANIZATION_ID,
        role=Role.OWNER,
        now=NOW,
    )

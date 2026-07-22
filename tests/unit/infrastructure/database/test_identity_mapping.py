"""Identity persistence mapping tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Table
from workflowforge_application.identity import PasswordCredential
from workflowforge_domain.identity import (
    AuthSession,
    EmailAddress,
    InvalidTimestamp,
    Membership,
    Organization,
    OrganizationSlug,
    RefreshTokenDigest,
    RefreshTokenFamilyId,
    RefreshTokenId,
    RefreshTokenRecord,
    Role,
    SessionId,
    User,
)
from workflowforge_infrastructure.identity.models import (
    AuthSessionRecord,
    MembershipRecord,
    OrganizationRecord,
    PasswordCredentialRecord,
    RefreshTokenRecordModel,
    UserRecord,
)
from workflowforge_infrastructure.identity.repository import (
    _auth_session_from_record,
    _membership_from_record,
    _organization_from_record,
    _password_credential_from_record,
    _record_from_auth_session,
    _record_from_membership,
    _record_from_organization,
    _record_from_password_credential,
    _record_from_refresh_token,
    _record_from_user,
    _refresh_token_from_record,
    _user_from_record,
)

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORGANIZATION_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("55555555-5555-4555-8555-555555555555")
FAMILY_ID = UUID("66666666-6666-4666-8666-666666666666")
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


def test_password_credential_record_mapping_round_trips_without_repr_leak() -> None:
    credential = PasswordCredential(
        user_id=USER_ID,
        password_hash="$argon2id$stored-secret",
        created_at=NOW,
        updated_at=NOW,
    )

    record = _record_from_password_credential(credential)
    mapped = _password_credential_from_record(record)

    assert isinstance(record, PasswordCredentialRecord)
    assert record.password_hash == "$argon2id$stored-secret"
    assert mapped == credential
    assert "stored-secret" not in repr(mapped)


def test_auth_session_record_mapping_round_trips_domain_values() -> None:
    session = _auth_session()

    record = _record_from_auth_session(session)
    mapped = _auth_session_from_record(record)

    assert isinstance(record, AuthSessionRecord)
    assert record.user_id == USER_ID
    assert mapped == session


def test_refresh_token_record_mapping_round_trips_without_digest_repr_leak() -> None:
    token = _refresh_token()

    record = _record_from_refresh_token(token)
    mapped = _refresh_token_from_record(record)

    assert isinstance(record, RefreshTokenRecordModel)
    assert record.token_hash == "a" * 64
    assert mapped == token
    assert "a" * 64 not in repr(mapped)


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

    assert PasswordCredentialRecord.__table__.c.user_id.primary_key is True
    assert PasswordCredentialRecord.__table__.c.password_hash.nullable is False
    assert AuthSessionRecord.__table__.c.user_id.nullable is False
    assert RefreshTokenRecordModel.__table__.c.token_hash.unique is None
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


def _auth_session() -> AuthSession:
    return AuthSession.create(
        id=SessionId(SESSION_ID),
        user_id=USER_ID,
        now=NOW,
        expires_at=NOW.replace(hour=4),
    )


def _refresh_token() -> RefreshTokenRecord:
    return RefreshTokenRecord.issue_initial(
        id=RefreshTokenId(TOKEN_ID),
        session_id=SessionId(SESSION_ID),
        token_family_id=RefreshTokenFamilyId(FAMILY_ID),
        token_digest=RefreshTokenDigest("a" * 64),
        issued_at=NOW,
        expires_at=NOW.replace(hour=4),
    )

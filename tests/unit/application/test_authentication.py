"""Email/password authentication application tests."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from workflowforge_application.identity import (
    AuthenticateUser,
    AuthenticateUserCommand,
    InvalidCredentialsError,
    InvalidPasswordError,
    PasswordCredential,
    SetUserPassword,
    SetUserPasswordCommand,
    UserAuthenticationDisabledError,
)
from workflowforge_domain.identity import EmailAddress, User

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.asyncio
async def test_valid_active_user_authenticates_with_normalized_email() -> None:
    users = FakeUserRepository([_user(email="Ada@Example.com")])
    credentials = FakePasswordCredentialRepository(
        [PasswordCredential(USER_ID, "hash:passphrase-123", NOW, NOW)]
    )
    use_case = AuthenticateUser(
        users=users,
        credentials=credentials,
        password_hasher=FakePasswordHasher(),
    )

    result = await use_case(AuthenticateUserCommand(" ada@example.COM ", "passphrase-123"))

    assert result.user_id == USER_ID
    assert result.email == "ada@example.com"
    assert result.display_name == "Ada Lovelace"
    assert result.is_active is True
    assert "password_hash" not in {field.name for field in fields(result)}
    assert users.lookup_values == ["ada@example.com"]


@pytest.mark.asyncio
async def test_unknown_email_wrong_password_and_missing_credential_fail_generically() -> None:
    hasher = FakePasswordHasher()
    users = FakeUserRepository([_user()])

    unknown = AuthenticateUser(
        users=users,
        credentials=FakePasswordCredentialRepository([]),
        password_hasher=hasher,
    )
    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        await unknown(AuthenticateUserCommand("unknown@example.com", "passphrase-123"))

    missing_credential = AuthenticateUser(
        users=users,
        credentials=FakePasswordCredentialRepository([]),
        password_hasher=hasher,
    )
    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        await missing_credential(AuthenticateUserCommand("ada@example.com", "passphrase-123"))

    wrong_password = AuthenticateUser(
        users=users,
        credentials=FakePasswordCredentialRepository(
            [PasswordCredential(USER_ID, "hash:correct-password", NOW, NOW)]
        ),
        password_hasher=hasher,
    )
    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        await wrong_password(AuthenticateUserCommand("ada@example.com", "wrong-password"))

    assert hasher.dummy_verifications == 2


@pytest.mark.asyncio
async def test_invalid_email_and_hasher_failures_are_sanitized() -> None:
    use_case = AuthenticateUser(
        users=FakeUserRepository([_user()]),
        credentials=FakePasswordCredentialRepository(
            [PasswordCredential(USER_ID, "raise", NOW, NOW)]
        ),
        password_hasher=FakePasswordHasher(),
    )

    with pytest.raises(InvalidCredentialsError) as invalid_email:
        await use_case(AuthenticateUserCommand("not-an-email", "secret-password"))
    with pytest.raises(InvalidCredentialsError) as verify_failure:
        await use_case(AuthenticateUserCommand("ada@example.com", "secret-password"))

    assert "secret-password" not in str(invalid_email.value)
    assert "secret-password" not in str(verify_failure.value)


@pytest.mark.asyncio
async def test_inactive_user_with_valid_password_cannot_authenticate() -> None:
    users = FakeUserRepository([_user().disable(now=NOW + timedelta(seconds=1))])
    use_case = AuthenticateUser(
        users=users,
        credentials=FakePasswordCredentialRepository(
            [PasswordCredential(USER_ID, "hash:passphrase-123", NOW, NOW)]
        ),
        password_hasher=FakePasswordHasher(),
    )

    with pytest.raises(UserAuthenticationDisabledError):
        await use_case(AuthenticateUserCommand("ada@example.com", "passphrase-123"))


@pytest.mark.asyncio
async def test_set_user_password_hashes_and_replaces_credential() -> None:
    users = FakeUserRepository([_user()])
    credentials = FakePasswordCredentialRepository([])
    use_case = SetUserPassword(
        users=users,
        credentials=credentials,
        password_hasher=FakePasswordHasher(),
    )

    created = await use_case(
        SetUserPasswordCommand(USER_ID, "long-passphrase"),
        now=NOW,
    )
    replaced = await use_case(
        SetUserPasswordCommand(USER_ID, "replacement-passphrase"),
        now=NOW + timedelta(seconds=1),
    )

    assert created.password_hash == "hash:long-passphrase"
    assert replaced.password_hash == "hash:replacement-passphrase"
    assert replaced.created_at == NOW
    assert replaced.updated_at == NOW + timedelta(seconds=1)
    assert credentials.records[USER_ID] == replaced


@pytest.mark.asyncio
async def test_password_policy_is_separate_from_hasher() -> None:
    use_case = SetUserPassword(
        users=FakeUserRepository([_user()]),
        credentials=FakePasswordCredentialRepository([]),
        password_hasher=FakePasswordHasher(),
    )

    with pytest.raises(InvalidPasswordError, match="at least 12"):
        await use_case(SetUserPasswordCommand(USER_ID, "too-short"), now=NOW)

    with pytest.raises(InvalidPasswordError, match="at most 256"):
        await use_case(SetUserPasswordCommand(USER_ID, "a" * 257), now=NOW)


def test_password_credential_repr_does_not_expose_hash() -> None:
    credential = PasswordCredential(USER_ID, "hash:secret-password", NOW, NOW)

    assert "secret-password" not in repr(credential)
    assert "password_hash" not in repr(credential)


class FakePasswordHasher:
    def __init__(self) -> None:
        self.dummy_verifications = 0

    def hash_password(self, plain_password: str) -> str:
        return f"hash:{plain_password}"

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        if password_hash == "raise":
            raise RuntimeError("stored credential failure")
        if password_hash == self.dummy_password_hash():
            self.dummy_verifications += 1
            return False
        return password_hash == f"hash:{plain_password}"

    def dummy_password_hash(self) -> str:
        return "hash:dummy-password"


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self.records = {user.id: user for user in users}
        self.email_records = {user.email.normalized: user for user in users}
        self.lookup_values: list[str] = []

    async def add(self, user: User) -> User:
        self.records[user.id] = user
        self.email_records[user.email.normalized] = user
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.records.get(user_id)

    async def get_by_normalized_email(self, email: EmailAddress | str) -> User | None:
        normalized = email.normalized if isinstance(email, EmailAddress) else email
        self.lookup_values.append(normalized)
        return self.email_records.get(normalized)

    async def update(self, user: User) -> User:
        self.records[user.id] = user
        self.email_records[user.email.normalized] = user
        return user


class FakePasswordCredentialRepository:
    def __init__(self, credentials: list[PasswordCredential]) -> None:
        self.records = {credential.user_id: credential for credential in credentials}

    async def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        return self.records.get(user_id)

    async def set_for_user(self, credential: PasswordCredential) -> PasswordCredential:
        self.records[credential.user_id] = credential
        return credential


def _user(*, email: str = "ada@example.com") -> User:
    return User.create(
        id=USER_ID,
        email=EmailAddress(email),
        display_name="Ada Lovelace",
        now=NOW,
    )

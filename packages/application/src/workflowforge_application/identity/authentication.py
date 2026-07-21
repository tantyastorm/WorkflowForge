"""Email/password authentication use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from workflowforge_domain.identity import EmailAddress
from workflowforge_domain.identity.errors import InvalidEmailAddress

from workflowforge_application.identity.credentials import PasswordCredential
from workflowforge_application.identity.errors import (
    InvalidCredentialsError,
    InvalidPasswordError,
    MissingIdentityReferenceError,
    UserAuthenticationDisabledError,
)
from workflowforge_application.identity.ports import (
    PasswordCredentialRepository,
    PasswordHasher,
    UserRepository,
)

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256


@dataclass(frozen=True, slots=True)
class AuthenticateUserCommand:
    """Input for email/password authentication."""

    email: str
    password: str


@dataclass(frozen=True, slots=True)
class SetUserPasswordCommand:
    """Input for creating or replacing a user password credential."""

    user_id: UUID
    password: str


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Safe authentication result without credential or session material."""

    user_id: UUID
    email: str
    display_name: str
    is_active: bool


class AuthenticateUser:
    """Authenticate a user by normalized email and password."""

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: PasswordCredentialRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._password_hasher = password_hasher

    async def __call__(self, command: AuthenticateUserCommand) -> AuthenticatedUser:
        """Return a safe principal or raise a sanitized authentication error."""

        try:
            email = EmailAddress(command.email)
        except InvalidEmailAddress as exc:
            self._verify_dummy(command.password)
            msg = "Invalid email or password."
            raise InvalidCredentialsError(msg) from exc

        user = await self._users.get_by_normalized_email(email)
        if user is None:
            self._verify_dummy(command.password)
            msg = "Invalid email or password."
            raise InvalidCredentialsError(msg)

        credential = await self._credentials.get_by_user_id(user.id)
        if credential is None:
            self._verify_dummy(command.password)
            msg = "Invalid email or password."
            raise InvalidCredentialsError(msg)

        if not self._verify(command.password, credential.password_hash):
            msg = "Invalid email or password."
            raise InvalidCredentialsError(msg)

        if not user.is_active:
            msg = "User is not allowed to authenticate."
            raise UserAuthenticationDisabledError(msg)

        return AuthenticatedUser(
            user_id=user.id,
            email=user.email.normalized,
            display_name=user.display_name,
            is_active=user.is_active,
        )

    def _verify_dummy(self, plain_password: str) -> None:
        self._verify(plain_password, self._password_hasher.dummy_password_hash())

    def _verify(self, plain_password: str, password_hash: str) -> bool:
        try:
            return self._password_hasher.verify_password(plain_password, password_hash)
        except Exception as exc:
            msg = "Invalid email or password."
            raise InvalidCredentialsError(msg) from exc


class SetUserPassword:
    """Create or replace a user's password credential."""

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: PasswordCredentialRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._password_hasher = password_hasher

    async def __call__(
        self,
        command: SetUserPasswordCommand,
        *,
        now: datetime | None = None,
    ) -> PasswordCredential:
        """Hash and persist a password credential for an existing user."""

        _validate_password_policy(command.password)
        user = await self._users.get_by_id(command.user_id)
        if user is None:
            msg = "User does not exist."
            raise MissingIdentityReferenceError(msg)

        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        password_hash = self._password_hasher.hash_password(command.password)
        existing = await self._credentials.get_by_user_id(command.user_id)
        credential = (
            existing.replace_hash(password_hash, now=timestamp)
            if existing is not None
            else PasswordCredential(
                user_id=command.user_id,
                password_hash=password_hash,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        return await self._credentials.set_for_user(credential)


def _validate_password_policy(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        msg = f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
        raise InvalidPasswordError(msg)
    if len(password) > PASSWORD_MAX_LENGTH:
        msg = f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
        raise InvalidPasswordError(msg)

"""Password hashing adapters."""

from __future__ import annotations

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from workflowforge_domain.identity import RefreshTokenDigest


class Argon2PasswordHasher:
    """Argon2id password hasher implementation."""

    _dummy_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$"
        "WmF3ZGV2ZHVtbXlzYWx0MQ$"
        "yeOQ2hErJ0XAC+JtSMZPEQajnjCt6apO07B7uh74DQA"
    )

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=Type.ID,
        )

    def __repr__(self) -> str:
        return "Argon2PasswordHasher(algorithm='argon2id')"

    def hash_password(self, plain_password: str) -> str:
        """Return an Argon2id password hash."""

        return self._hasher.hash(plain_password)

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """Return whether a plaintext password matches a stored hash."""

        try:
            return self._hasher.verify(password_hash, plain_password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def dummy_password_hash(self) -> str:
        """Return a stable dummy hash for missing-account verification."""

        return self._dummy_hash

    def needs_rehash(self, password_hash: str) -> bool:
        """Return whether a stored hash should be replaced with current parameters."""

        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (InvalidHashError, VerificationError):
            return False


class Sha256RefreshTokenHasher:
    """SHA-256 digest adapter for high-entropy opaque refresh tokens."""

    def __repr__(self) -> str:
        return "Sha256RefreshTokenHasher(algorithm='sha256')"

    def digest_token(self, plain_token: str) -> RefreshTokenDigest:
        """Return a deterministic SHA-256 digest for a refresh token."""

        return RefreshTokenDigest(hashlib.sha256(plain_token.encode("utf-8")).hexdigest())

    def verify_token(self, plain_token: str, token_digest: RefreshTokenDigest) -> bool:
        """Return whether a plaintext refresh token matches a stored digest."""

        expected = self.digest_token(plain_token)
        return hmac.compare_digest(expected.value, token_digest.value)

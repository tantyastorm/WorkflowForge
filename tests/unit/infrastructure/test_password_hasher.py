"""Password hasher adapter tests."""

import pytest
from workflowforge_infrastructure.identity import Argon2PasswordHasher, Sha256RefreshTokenHasher


def test_argon2id_hasher_hashes_and_verifies_passwords() -> None:
    hasher = Argon2PasswordHasher()
    plain_password = "correct horse battery staple"

    first_hash = hasher.hash_password(plain_password)
    second_hash = hasher.hash_password(plain_password)

    assert first_hash != plain_password
    assert first_hash != second_hash
    assert first_hash.startswith("$argon2id$")
    assert second_hash.startswith("$argon2id$")
    assert hasher.verify_password(plain_password, first_hash) is True
    assert hasher.verify_password("wrong password", first_hash) is False


@pytest.mark.parametrize("stored_hash", ["", "not-a-hash", "$argon2i$v=19$bad"])
def test_argon2id_hasher_malformed_hashes_fail_safely(stored_hash: str) -> None:
    hasher = Argon2PasswordHasher()

    assert hasher.verify_password("any-password", stored_hash) is False


def test_argon2id_hasher_repr_and_errors_do_not_expose_plaintext() -> None:
    hasher = Argon2PasswordHasher()
    plain_password = "do-not-leak-this-passphrase"

    assert plain_password not in repr(hasher)
    assert hasher.verify_password(plain_password, "not-a-hash") is False


def test_argon2id_hasher_exposes_dummy_hash_and_rehash_check() -> None:
    hasher = Argon2PasswordHasher()

    assert hasher.dummy_password_hash().startswith("$argon2id$")
    assert hasher.verify_password("anything", hasher.dummy_password_hash()) is False
    assert hasher.needs_rehash("not-a-hash") is False


def test_sha256_refresh_token_hasher_digests_and_verifies_without_repr_leak() -> None:
    hasher = Sha256RefreshTokenHasher()
    plain_token = "high-entropy-refresh-token"

    digest = hasher.digest_token(plain_token)

    assert digest.value == hasher.digest_token(plain_token).value
    assert digest.value != plain_token
    assert len(digest.value) == 64
    assert hasher.verify_token(plain_token, digest) is True
    assert hasher.verify_token("wrong-token", digest) is False
    assert plain_token not in repr(hasher)
    assert digest.value not in repr(digest)

"""Password hasher adapter tests."""

import pytest
from workflowforge_infrastructure.identity import Argon2PasswordHasher


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

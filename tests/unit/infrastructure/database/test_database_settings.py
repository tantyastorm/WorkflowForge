"""Database settings tests."""

import pytest
from pydantic import SecretStr, ValidationError
from workflowforge_infrastructure.config import DatabaseSettings, Settings

DATABASE_ENVIRONMENT_VARIABLES = (
    "WORKFLOWFORGE_DATABASE_HOST",
    "WORKFLOWFORGE_DATABASE_PORT",
    "WORKFLOWFORGE_DATABASE_NAME",
    "WORKFLOWFORGE_DATABASE_USER",
    "WORKFLOWFORGE_DATABASE_PASSWORD",
    "WORKFLOWFORGE_DATABASE_ECHO",
    "WORKFLOWFORGE_DATABASE_POOL_SIZE",
    "WORKFLOWFORGE_DATABASE_MAX_OVERFLOW",
    "WORKFLOWFORGE_DATABASE_POOL_TIMEOUT_SECONDS",
)


def test_database_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_database_environment(monkeypatch)

    settings = DatabaseSettings()

    assert settings.host == "localhost"
    assert settings.port == 5432
    assert settings.name == "workflowforge"
    assert settings.user == "workflowforge"
    assert settings.password.get_secret_value() == "workflowforge"
    assert settings.echo is False
    assert settings.pool_size == 5
    assert settings.max_overflow == 10
    assert settings.pool_timeout_seconds == 30


def test_database_settings_ignore_generic_os_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_database_environment(monkeypatch)
    monkeypatch.setenv("HOST", "bad-host")
    monkeypatch.setenv("PORT", "15432")
    monkeypatch.setenv("NAME", "bad-name")
    monkeypatch.setenv("USER", "runner")
    monkeypatch.setenv("PASSWORD", "bad-password")

    settings = DatabaseSettings()

    assert settings.host == "localhost"
    assert settings.port == 5432
    assert settings.name == "workflowforge"
    assert settings.user == "workflowforge"
    assert settings.password.get_secret_value() == "workflowforge"


def test_database_settings_accept_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_database_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_HOST", "postgres.local")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PORT", "15432")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_NAME", "workflowforge_test")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_USER", "tester")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PASSWORD", "testing")

    settings = DatabaseSettings()

    assert settings.host == "postgres.local"
    assert settings.port == 15432
    assert settings.name == "workflowforge_test"
    assert settings.user == "tester"
    assert settings.password.get_secret_value() == "testing"


def test_database_urls_use_expected_drivers_and_encode_password() -> None:
    settings = DatabaseSettings(
        host="db.example.test",
        port=15432,
        name="workflowforge",
        user="workflowforge",
        password=SecretStr("p@ss/word"),
    )

    async_url = settings.async_sqlalchemy_url().render_as_string(hide_password=False)
    sync_url = settings.sync_sqlalchemy_url().render_as_string(hide_password=False)

    assert async_url == (
        "postgresql+asyncpg://workflowforge:p%40ss%2Fword@db.example.test:15432/workflowforge"
    )
    assert sync_url == (
        "postgresql+psycopg://workflowforge:p%40ss%2Fword@db.example.test:15432/workflowforge"
    )


def test_database_password_repr_is_safe() -> None:
    settings = DatabaseSettings(password=SecretStr("super-secret"))

    assert "super-secret" not in repr(settings)
    assert "**********" in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 0),
        ("port", 65536),
        ("name", ""),
        ("user", ""),
        ("pool_size", 0),
        ("max_overflow", -1),
        ("pool_timeout_seconds", 0),
    ],
)
def test_database_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings.model_validate({field: value})


def test_nested_database_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_database_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_HOST", "postgres.local")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PORT", "15432")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_NAME", "workflowforge_test")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_USER", "tester")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PASSWORD", "testing")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_ECHO", "true")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_POOL_SIZE", "2")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_MAX_OVERFLOW", "3")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_POOL_TIMEOUT_SECONDS", "4.5")

    settings = Settings()

    assert settings.database.host == "postgres.local"
    assert settings.database.port == 15432
    assert settings.database.name == "workflowforge_test"
    assert settings.database.user == "tester"
    assert settings.database.password.get_secret_value() == "testing"
    assert settings.database.echo is True
    assert settings.database.pool_size == 2
    assert settings.database.max_overflow == 3
    assert settings.database.pool_timeout_seconds == 4.5


def clear_database_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in DATABASE_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

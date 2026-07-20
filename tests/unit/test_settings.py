"""Settings validation tests."""

import pytest
from pydantic import ValidationError
from workflowforge_infrastructure.config.settings import (
    ApiSettings,
    Environment,
    LogFormat,
    LogLevel,
    Settings,
)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFLOWFORGE_APP_NAME", raising=False)
    monkeypatch.delenv("WORKFLOWFORGE_ENVIRONMENT", raising=False)
    monkeypatch.delenv("WORKFLOWFORGE_DEBUG", raising=False)
    monkeypatch.delenv("WORKFLOWFORGE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("WORKFLOWFORGE_LOG_FORMAT", raising=False)

    settings = Settings()

    assert settings.app_name == "WorkflowForge"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is True
    assert settings.log_level is LogLevel.INFO
    assert settings.log_format is LogFormat.CONSOLE
    assert settings.api.host == "0.0.0.0"
    assert settings.api.port == 8000
    assert settings.api.v1_prefix == "/api/v1"
    assert settings.api.docs_enabled is True
    assert settings.cors_origins == ("http://localhost:5173",)


def test_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_APP_NAME", "WorkflowForge Tests")
    monkeypatch.setenv("WORKFLOWFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKFLOWFORGE_DEBUG", "false")
    monkeypatch.setenv("WORKFLOWFORGE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("WORKFLOWFORGE_LOG_FORMAT", "json")

    settings = Settings()

    assert settings.app_name == "WorkflowForge Tests"
    assert settings.environment is Environment.TEST
    assert settings.debug is False
    assert settings.log_level is LogLevel.DEBUG
    assert settings.log_format is LogFormat.JSON


def test_api_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_API_HOST", "127.0.0.1")
    monkeypatch.setenv("WORKFLOWFORGE_API_PORT", "9000")
    monkeypatch.setenv("WORKFLOWFORGE_API_V1_PREFIX", "/custom/v1")
    monkeypatch.setenv("WORKFLOWFORGE_API_DOCS_ENABLED", "false")
    monkeypatch.setenv("WORKFLOWFORGE_CORS_ORIGINS", "http://one.local, http://two.local")

    settings = Settings()

    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 9000
    assert settings.api.v1_prefix == "/custom/v1"
    assert settings.api.docs_enabled is False
    assert settings.cors_origins == ("http://one.local", "http://two.local")


def test_api_port_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(port=0)


def test_api_prefix_must_begin_with_slash() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(v1_prefix="api/v1")


def test_api_prefix_must_not_end_with_slash() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(v1_prefix="/api/v1/")


def test_api_prefix_must_not_be_root() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(v1_prefix="/")


def test_empty_cors_origins_are_deliberately_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_CORS_ORIGINS", "")

    settings = Settings()

    assert settings.cors_origins == ()


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins=("*",))


def test_settings_reject_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_ENVIRONMENT", "staging")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_invalid_log_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_LOG_FORMAT", "plain")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_ignore_unrelated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNRELATED_APP_NAME", "Ignored")

    settings = Settings()

    assert settings.app_name == "WorkflowForge"

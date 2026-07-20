"""Settings validation tests."""

import pytest
from pydantic import ValidationError
from workflowforge_infrastructure.config.settings import (
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

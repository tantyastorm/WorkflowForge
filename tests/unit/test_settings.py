"""Settings validation tests."""

import pytest
from pydantic import SecretStr, ValidationError
from workflowforge_infrastructure.config.settings import (
    ApiSettings,
    Environment,
    LogFormat,
    LogLevel,
    RedisSettings,
    S3Settings,
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
    assert settings.redis.host == "localhost"
    assert settings.redis.port == 6379
    assert settings.redis.db == 0
    assert settings.redis.password is None
    assert settings.redis.ssl is False
    assert settings.redis.socket_timeout_seconds == 3
    assert settings.s3.endpoint_url == "http://localhost:9000"
    assert settings.s3.bucket == "workflowforge"
    assert settings.s3.access_key == "workflowforge"
    assert settings.s3.secret_key.get_secret_value() == "workflowforge_dev_secret"
    assert settings.s3.region == "us-east-1"
    assert settings.s3.use_ssl is False
    assert settings.s3.timeout_seconds == 3


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


def test_redis_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_HOST", "localhost")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_PORT", "16379")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_DB", "2")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_PASSWORD", "redis-secret")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_SSL", "true")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_SOCKET_TIMEOUT_SECONDS", "1.5")

    settings = Settings()

    assert settings.redis.host == "localhost"
    assert settings.redis.port == 16379
    assert settings.redis.db == 2
    assert settings.redis.password is not None
    assert settings.redis.password.get_secret_value() == "redis-secret"
    assert settings.redis.ssl is True
    assert settings.redis.socket_timeout_seconds == 1.5


def test_empty_redis_password_is_none() -> None:
    settings = RedisSettings.model_validate({"password": ""})

    assert settings.password is None


def test_redis_password_repr_is_safe() -> None:
    settings = RedisSettings(password=SecretStr("super-secret"))

    assert "super-secret" not in repr(settings)
    assert "**********" in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 0),
        ("db", -1),
        ("socket_timeout_seconds", 0),
    ],
)
def test_redis_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        RedisSettings.model_validate({field: value})


def test_s3_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_S3_ENDPOINT_URL", "http://localhost:19000")
    monkeypatch.setenv("WORKFLOWFORGE_S3_ACCESS_KEY", "access")
    monkeypatch.setenv("WORKFLOWFORGE_S3_SECRET_KEY", "storage-secret")
    monkeypatch.setenv("WORKFLOWFORGE_S3_BUCKET", "bucket")
    monkeypatch.setenv("WORKFLOWFORGE_S3_REGION", "eu-test-1")
    monkeypatch.setenv("WORKFLOWFORGE_S3_USE_SSL", "true")
    monkeypatch.setenv("WORKFLOWFORGE_S3_TIMEOUT_SECONDS", "2.5")

    settings = Settings()

    assert settings.s3.endpoint_url == "http://localhost:19000"
    assert settings.s3.access_key == "access"
    assert settings.s3.secret_key.get_secret_value() == "storage-secret"
    assert settings.s3.bucket == "bucket"
    assert settings.s3.region == "eu-test-1"
    assert settings.s3.use_ssl is True
    assert settings.s3.timeout_seconds == 2.5


def test_s3_secret_key_repr_is_safe() -> None:
    settings = S3Settings(secret_key=SecretStr("super-secret"))

    assert "super-secret" not in repr(settings)
    assert "**********" in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint_url", "minio:9000"),
        ("access_key", ""),
        ("bucket", ""),
        ("timeout_seconds", 0),
    ],
)
def test_s3_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        S3Settings.model_validate({field: value})


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

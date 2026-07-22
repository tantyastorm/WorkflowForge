"""Settings validation tests."""

import pytest
from pydantic import SecretStr, ValidationError
from workflowforge_infrastructure.config.settings import (
    ApiSettings,
    AuthSettings,
    CelerySettings,
    CleanupSettings,
    Environment,
    LogFormat,
    LogLevel,
    RateLimitFailurePolicy,
    RateLimitSettings,
    RedisSettings,
    S3Settings,
    SchedulerSettings,
    Settings,
)

AUTH_ENVIRONMENT_VARIABLES = (
    "WORKFLOWFORGE_AUTH_JWT_ALGORITHM",
    "WORKFLOWFORGE_AUTH_JWT_ISSUER",
    "WORKFLOWFORGE_AUTH_JWT_AUDIENCE",
    "WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET",
    "WORKFLOWFORGE_AUTH_ACCESS_TOKEN_LIFETIME_SECONDS",
    "WORKFLOWFORGE_AUTH_REFRESH_TOKEN_LIFETIME_SECONDS",
    "WORKFLOWFORGE_AUTH_SESSION_LIFETIME_SECONDS",
    "WORKFLOWFORGE_AUTH_REFRESH_TOKEN_BYTES",
    "WORKFLOWFORGE_AUTH_REFRESH_COOKIE_NAME",
    "WORKFLOWFORGE_AUTH_REFRESH_COOKIE_PATH",
    "WORKFLOWFORGE_AUTH_REFRESH_COOKIE_SECURE",
    "WORKFLOWFORGE_AUTH_REFRESH_COOKIE_SAMESITE",
    "WORKFLOWFORGE_AUTH_CSRF_COOKIE_NAME",
    "WORKFLOWFORGE_AUTH_CSRF_HEADER_NAME",
)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
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
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
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
    assert settings.celery.resolved_broker_url(settings.redis) == "redis://localhost:6379/1"
    assert settings.celery.resolved_result_backend(settings.redis) == "redis://localhost:6379/2"
    assert settings.celery.default_queue == "workflowforge"
    assert settings.celery.diagnostic_queue == "workflowforge.diagnostics"
    assert settings.celery.task_time_limit_seconds == 300
    assert settings.celery.task_soft_time_limit_seconds == 270
    assert settings.celery.worker_concurrency == 2
    assert settings.celery.worker_health_timeout_seconds == 3
    assert settings.scheduler.heartbeat_interval_seconds == 30
    assert settings.scheduler.heartbeat_ttl_seconds == 90
    assert settings.scheduler.heartbeat_key == "workflowforge:diagnostics:scheduler:last_seen"
    assert settings.rate_limit.login_identifier_threshold == 5
    assert settings.rate_limit.login_client_threshold == 20
    assert settings.rate_limit.login_window_seconds == 900
    assert settings.rate_limit.refresh_client_threshold == 10
    assert settings.rate_limit.refresh_window_seconds == 300
    assert settings.rate_limit.failure_policy is RateLimitFailurePolicy.OPEN
    assert settings.cleanup.session_batch_limit == 500
    assert settings.cleanup.expired_session_retention_seconds == 604_800
    assert settings.cleanup.revoked_session_retention_seconds == 2_592_000
    assert settings.cleanup.schedule_enabled is False
    assert settings.cleanup.schedule_seconds == 3600
    assert settings.auth.jwt_algorithm == "HS256"
    assert settings.auth.jwt_issuer == "workflowforge"
    assert settings.auth.jwt_audience == "workflowforge-api"
    assert settings.auth.access_token_lifetime_seconds == 900
    assert settings.auth.refresh_token_lifetime_seconds == 2_592_000
    assert settings.auth.session_lifetime_seconds == 2_592_000
    assert settings.auth.refresh_token_bytes == 32
    assert settings.auth.refresh_cookie_name == "workflowforge_refresh"
    assert settings.auth.refresh_cookie_path == "/api/v1/auth"
    assert settings.auth.refresh_cookie_secure is False
    assert settings.auth.refresh_cookie_samesite == "lax"
    assert settings.auth.csrf_cookie_name == "workflowforge_csrf"
    assert settings.auth.csrf_header_name == "X-CSRF-Token"


def test_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
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


def test_celery_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_HOST", "redis")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_PORT", "6380")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_BROKER_DATABASE", "4")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_RESULT_BACKEND_DATABASE", "5")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_DEFAULT_QUEUE", "default.queue")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_DIAGNOSTIC_QUEUE", "diagnostic.queue")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_TASK_TIME_LIMIT_SECONDS", "60")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_TASK_SOFT_TIME_LIMIT_SECONDS", "45")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_WORKER_CONCURRENCY", "3")
    monkeypatch.setenv("WORKFLOWFORGE_CELERY_WORKER_HEALTH_TIMEOUT_SECONDS", "1.5")

    settings = Settings()

    assert settings.celery.resolved_broker_url(settings.redis) == "redis://redis:6380/4"
    assert settings.celery.resolved_result_backend(settings.redis) == "redis://redis:6380/5"
    assert settings.celery.default_queue == "default.queue"
    assert settings.celery.diagnostic_queue == "diagnostic.queue"
    assert settings.celery.task_time_limit_seconds == 60
    assert settings.celery.task_soft_time_limit_seconds == 45
    assert settings.celery.worker_concurrency == 3
    assert settings.celery.worker_health_timeout_seconds == 1.5


def test_celery_explicit_urls_are_supported_and_redacted() -> None:
    settings = CelerySettings(
        broker_url=SecretStr("redis://:secret@redis:6379/1"),
        result_backend=SecretStr("redis://:secret@redis:6379/2"),
    )
    redis_settings = RedisSettings(host="ignored")

    assert settings.resolved_broker_url(redis_settings) == "redis://:secret@redis:6379/1"
    assert settings.resolved_result_backend(redis_settings) == "redis://:secret@redis:6379/2"
    assert "secret" not in repr(settings)
    assert "**********" in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("broker_url", "http://redis:6379/1"),
        ("result_backend", "postgresql://db"),
        ("default_queue", "bad queue"),
        ("diagnostic_queue", "bad/queue"),
        ("task_time_limit_seconds", 0),
        ("task_soft_time_limit_seconds", 0),
        ("worker_concurrency", 0),
        ("worker_health_timeout_seconds", 0),
    ],
)
def test_celery_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        CelerySettings.model_validate({field: value})


def test_celery_soft_limit_must_be_lower_than_hard_limit() -> None:
    with pytest.raises(ValidationError):
        CelerySettings(task_time_limit_seconds=30, task_soft_time_limit_seconds=30)


def test_scheduler_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_SCHEDULER_HEARTBEAT_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("WORKFLOWFORGE_SCHEDULER_HEARTBEAT_TTL_SECONDS", "20")
    monkeypatch.setenv("WORKFLOWFORGE_SCHEDULER_HEARTBEAT_KEY", "workflowforge:test:last_seen")

    settings = Settings()

    assert settings.scheduler.heartbeat_interval_seconds == 5
    assert settings.scheduler.heartbeat_ttl_seconds == 20
    assert settings.scheduler.heartbeat_key == "workflowforge:test:last_seen"


def test_scheduler_heartbeat_ttl_must_exceed_interval() -> None:
    with pytest.raises(ValidationError):
        SchedulerSettings(heartbeat_interval_seconds=10, heartbeat_ttl_seconds=10)


def test_rate_limit_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_LOGIN_IDENTIFIER_THRESHOLD", "3")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_LOGIN_CLIENT_THRESHOLD", "7")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_REFRESH_CLIENT_THRESHOLD", "4")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_REFRESH_WINDOW_SECONDS", "30")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_FAILURE_POLICY", "closed")

    settings = Settings()

    assert settings.rate_limit.login_identifier_threshold == 3
    assert settings.rate_limit.login_client_threshold == 7
    assert settings.rate_limit.login_window_seconds == 60
    assert settings.rate_limit.refresh_client_threshold == 4
    assert settings.rate_limit.refresh_window_seconds == 30
    assert settings.rate_limit.failure_policy is RateLimitFailurePolicy.CLOSED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("login_identifier_threshold", 0),
        ("login_identifier_threshold", 101),
        ("login_client_threshold", 0),
        ("login_client_threshold", 501),
        ("login_window_seconds", 0),
        ("login_window_seconds", 86_401),
        ("refresh_client_threshold", 0),
        ("refresh_client_threshold", 501),
        ("refresh_window_seconds", 0),
        ("refresh_window_seconds", 86_401),
        ("failure_policy", "sideways"),
    ],
)
def test_rate_limit_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        RateLimitSettings.model_validate({field: value})


def test_cleanup_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_CLEANUP_SESSION_BATCH_LIMIT", "250")
    monkeypatch.setenv("WORKFLOWFORGE_CLEANUP_EXPIRED_SESSION_RETENTION_SECONDS", "3600")
    monkeypatch.setenv("WORKFLOWFORGE_CLEANUP_REVOKED_SESSION_RETENTION_SECONDS", "7200")
    monkeypatch.setenv("WORKFLOWFORGE_CLEANUP_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("WORKFLOWFORGE_CLEANUP_SCHEDULE_SECONDS", "600")

    settings = Settings()

    assert settings.cleanup.session_batch_limit == 250
    assert settings.cleanup.expired_session_retention_seconds == 3600
    assert settings.cleanup.revoked_session_retention_seconds == 7200
    assert settings.cleanup.schedule_enabled is True
    assert settings.cleanup.schedule_seconds == 600


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_batch_limit", 0),
        ("session_batch_limit", 10_001),
        ("expired_session_retention_seconds", -1),
        ("revoked_session_retention_seconds", -1),
        ("schedule_seconds", 0),
    ],
)
def test_cleanup_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        CleanupSettings.model_validate({field: value})


def test_auth_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_JWT_ISSUER", "issuer")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_JWT_AUDIENCE", "audience")
    monkeypatch.setenv(
        "WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET",
        "override-secret-with-at-least-32-characters",
    )
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_ACCESS_TOKEN_LIFETIME_SECONDS", "60")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_TOKEN_LIFETIME_SECONDS", "120")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_SESSION_LIFETIME_SECONDS", "180")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_TOKEN_BYTES", "48")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_COOKIE_NAME", "refresh")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_COOKIE_PATH", "/custom/auth")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_COOKIE_SECURE", "true")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_COOKIE_SAMESITE", "strict")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_CSRF_COOKIE_NAME", "csrf")
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_CSRF_HEADER_NAME", "X-Test-CSRF")

    settings = Settings()

    assert settings.auth.jwt_issuer == "issuer"
    assert settings.auth.jwt_audience == "audience"
    assert settings.auth.jwt_signing_secret.get_secret_value().startswith("override")
    assert settings.auth.access_token_lifetime_seconds == 60
    assert settings.auth.refresh_token_lifetime_seconds == 120
    assert settings.auth.session_lifetime_seconds == 180
    assert settings.auth.refresh_token_bytes == 48
    assert settings.auth.refresh_cookie_name == "refresh"
    assert settings.auth.refresh_cookie_path == "/custom/auth"
    assert settings.auth.refresh_cookie_secure is True
    assert settings.auth.refresh_cookie_samesite == "strict"
    assert settings.auth.csrf_cookie_name == "csrf"
    assert settings.auth.csrf_header_name == "X-Test-CSRF"
    assert "override-secret" not in repr(settings.auth)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("jwt_algorithm", "none"),
        ("jwt_signing_secret", "too-short"),
        ("access_token_lifetime_seconds", 0),
        ("refresh_token_lifetime_seconds", 0),
        ("session_lifetime_seconds", 0),
        ("refresh_token_bytes", 31),
        ("refresh_cookie_name", "bad cookie"),
        ("refresh_cookie_path", "api/v1/auth"),
        ("refresh_cookie_samesite", "wide-open"),
        ("csrf_cookie_name", "bad cookie"),
        ("csrf_header_name", "Bad Header"),
    ],
)
def test_auth_settings_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        AuthSettings.model_validate({field: value})


def test_auth_refresh_lifetime_must_not_exceed_session_lifetime() -> None:
    with pytest.raises(ValidationError):
        AuthSettings(refresh_token_lifetime_seconds=120, session_lifetime_seconds=60)


def test_auth_cookie_names_must_not_collide() -> None:
    with pytest.raises(ValidationError, match="cookie names"):
        AuthSettings(
            refresh_cookie_name="workflowforge_auth",
            csrf_cookie_name="workflowforge_auth",
        )


def test_production_rejects_default_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_ENVIRONMENT", "production")

    with pytest.raises(ValidationError, match="JWT signing secret"):
        Settings()


def test_production_requires_secure_refresh_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET",
        "production-secret-with-at-least-32-characters",
    )

    with pytest.raises(ValidationError, match="Secure refresh cookies"):
        Settings()


def test_production_requires_debug_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    _set_minimal_production_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_DEBUG", "true")

    with pytest.raises(ValidationError, match="debug mode"):
        Settings()


def test_production_requires_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    _set_minimal_production_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PASSWORD", "")

    with pytest.raises(ValidationError, match="database password"):
        Settings()


def test_production_requires_redis_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    _set_minimal_production_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_PASSWORD", "")

    with pytest.raises(ValidationError, match="Redis authentication"):
        Settings()


def test_production_requires_fail_closed_rate_limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_auth_environment(monkeypatch)
    _set_minimal_production_environment(monkeypatch)
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_FAILURE_POLICY", "open")

    with pytest.raises(ValidationError, match="fail-closed rate limiting"):
        Settings()


def test_production_accepts_hardened_security_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_auth_environment(monkeypatch)
    _set_minimal_production_environment(monkeypatch)

    settings = Settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.debug is False
    assert settings.auth.refresh_cookie_secure is True
    assert settings.redis.password is not None
    assert settings.rate_limit.failure_policy is RateLimitFailurePolicy.CLOSED


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


def test_nested_settings_ignore_generic_os_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_auth_environment(monkeypatch)
    generic_values = {
        "HOST": "bad-host",
        "PORT": "1",
        "NAME": "bad-name",
        "USER": "runner",
        "PASSWORD": "bad-password",
        "ACCESS_KEY": "bad-access",
        "SECRET_KEY": "bad-secret",
        "BUCKET": "bad-bucket",
        "REGION": "bad-region",
        "DEFAULT_QUEUE": "bad.queue",
        "HEARTBEAT_INTERVAL_SECONDS": "1",
    }
    for key, value in generic_values.items():
        monkeypatch.setenv(key, value)

    settings = Settings()

    assert settings.api.host == "0.0.0.0"
    assert settings.api.port == 8000
    assert settings.database.user == "workflowforge"
    assert settings.redis.host == "localhost"
    assert settings.s3.secret_key.get_secret_value() == "workflowforge_dev_secret"
    assert settings.celery.default_queue == "workflowforge"
    assert settings.scheduler.heartbeat_interval_seconds == 30


def clear_auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in AUTH_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def _set_minimal_production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWFORGE_ENVIRONMENT", "production")
    monkeypatch.setenv("WORKFLOWFORGE_DEBUG", "false")
    monkeypatch.setenv(
        "WORKFLOWFORGE_AUTH_JWT_SIGNING_SECRET",
        "production-secret-with-at-least-32-characters",
    )
    monkeypatch.setenv("WORKFLOWFORGE_AUTH_REFRESH_COOKIE_SECURE", "true")
    monkeypatch.setenv("WORKFLOWFORGE_DATABASE_PASSWORD", "database-secret")
    monkeypatch.setenv("WORKFLOWFORGE_REDIS_PASSWORD", "redis-secret")
    monkeypatch.setenv("WORKFLOWFORGE_RATE_LIMIT_FAILURE_POLICY", "closed")

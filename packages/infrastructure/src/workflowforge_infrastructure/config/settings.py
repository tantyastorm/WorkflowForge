"""WorkflowForge settings foundation."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL


class Environment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    """Supported log output formats."""

    CONSOLE = "console"
    JSON = "json"


class LogLevel(StrEnum):
    """Supported standard-library log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseSettings(BaseSettings):
    """Validated PostgreSQL database settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_DATABASE_",
        extra="forbid",
        validate_default=True,
    )

    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(default="workflowforge", min_length=1)
    user: str = Field(default="workflowforge", min_length=1)
    password: SecretStr = Field(default=SecretStr("workflowforge"))
    echo: bool = False
    pool_size: int = Field(default=5, gt=0)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)

    def async_sqlalchemy_url(self) -> URL:
        """Build the async SQLAlchemy URL for application runtime."""

        return self._url(drivername="postgresql+asyncpg")

    def sync_sqlalchemy_url(self) -> URL:
        """Build the synchronous SQLAlchemy URL for Alembic migrations."""

        return self._url(drivername="postgresql+psycopg")

    def _url(self, drivername: str) -> URL:
        return URL.create(
            drivername=drivername,
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.name,
        )


class ApiSettings(BaseSettings):
    """Validated API process settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_API_",
        extra="forbid",
        validate_default=True,
    )

    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    v1_prefix: str = "/api/v1"
    docs_enabled: bool = True

    @field_validator("v1_prefix")
    @classmethod
    def validate_v1_prefix(cls, value: str) -> str:
        """Require a normalized absolute API prefix."""

        if not value.startswith("/"):
            msg = "API prefix must begin with /"
            raise ValueError(msg)
        if value.endswith("/"):
            msg = "API prefix must not end with /"
            raise ValueError(msg)
        return value


class RedisSettings(BaseSettings):
    """Validated Redis infrastructure settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_REDIS_",
        extra="forbid",
        validate_default=True,
    )

    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    password: SecretStr | None = None
    ssl: bool = False
    socket_timeout_seconds: float = Field(default=3.0, gt=0)

    @field_validator("password", mode="before")
    @classmethod
    def empty_password_is_none(cls, value: object) -> object:
        """Treat empty Redis passwords as unset."""

        if value == "":
            return None
        return value


class S3Settings(BaseSettings):
    """Validated S3-compatible object storage settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_S3_",
        extra="forbid",
        validate_default=True,
    )

    endpoint_url: str = "http://localhost:9000"
    access_key: str = Field(default="workflowforge", min_length=1)
    secret_key: SecretStr = Field(default=SecretStr("workflowforge_dev_secret"))
    bucket: str = Field(default="workflowforge", min_length=1)
    region: str = Field(default="us-east-1", min_length=1)
    use_ssl: bool = False
    timeout_seconds: float = Field(default=3.0, gt=0)

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        """Require an HTTP(S) endpoint URL."""

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            msg = "S3 endpoint URL must be an absolute HTTP(S) URL"
            raise ValueError(msg)
        return value


class CelerySettings(BaseSettings):
    """Validated Celery task transport settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_CELERY_",
        extra="forbid",
        validate_default=True,
    )

    broker_url: SecretStr | None = None
    result_backend: SecretStr | None = None
    broker_database: int = Field(default=1, ge=0)
    result_backend_database: int = Field(default=2, ge=0)
    default_queue: str = Field(default="workflowforge", min_length=1)
    diagnostic_queue: str = Field(default="workflowforge.diagnostics", min_length=1)
    task_time_limit_seconds: int = Field(default=300, gt=0)
    task_soft_time_limit_seconds: int = Field(default=270, gt=0)
    worker_concurrency: int = Field(default=2, gt=0)
    worker_health_timeout_seconds: float = Field(default=3.0, gt=0)

    @field_validator("broker_url", "result_backend", mode="before")
    @classmethod
    def empty_url_is_none(cls, value: object) -> object:
        """Treat empty optional URL overrides as unset."""

        if value == "":
            return None
        return value

    @field_validator("broker_url", "result_backend")
    @classmethod
    def validate_redis_url(cls, value: SecretStr | None) -> SecretStr | None:
        """Require Redis URLs when explicit Celery URL overrides are used."""

        if value is None:
            return None
        parsed = urlparse(value.get_secret_value())
        if parsed.scheme not in {"redis", "rediss"} or not parsed.netloc:
            msg = "Celery broker and result backend URLs must be Redis URLs"
            raise ValueError(msg)
        return value

    @field_validator("default_queue", "diagnostic_queue")
    @classmethod
    def validate_queue_name(cls, value: str) -> str:
        """Require simple portable Celery queue names."""

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if any(character not in allowed for character in value):
            msg = (
                "Celery queue names may contain only letters, numbers, dots, "
                "underscores, and hyphens"
            )
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_time_limits(self) -> "CelerySettings":
        """Require the soft time limit to be lower than the hard time limit."""

        if self.task_soft_time_limit_seconds >= self.task_time_limit_seconds:
            msg = "Celery soft task time limit must be lower than the hard time limit"
            raise ValueError(msg)
        return self

    def resolved_broker_url(self, redis: RedisSettings) -> str:
        """Return the configured Celery broker URL."""

        if self.broker_url is not None:
            return self.broker_url.get_secret_value()
        return _redis_url(redis, db=self.broker_database)

    def resolved_result_backend(self, redis: RedisSettings) -> str:
        """Return the configured Celery result backend URL."""

        if self.result_backend is not None:
            return self.result_backend.get_secret_value()
        return _redis_url(redis, db=self.result_backend_database)


class SchedulerSettings(BaseSettings):
    """Validated scheduler process settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_SCHEDULER_",
        extra="forbid",
        validate_default=True,
    )

    heartbeat_interval_seconds: int = Field(default=30, gt=0)
    heartbeat_ttl_seconds: int = Field(default=90, gt=0)
    heartbeat_key: str = Field(
        default="workflowforge:diagnostics:scheduler:last_seen",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_heartbeat_policy(self) -> "SchedulerSettings":
        """Require heartbeat TTL to outlive the scheduler interval."""

        if self.heartbeat_ttl_seconds <= self.heartbeat_interval_seconds:
            msg = "Scheduler heartbeat TTL must be greater than the heartbeat interval"
            raise ValueError(msg)
        return self


DEFAULT_JWT_SIGNING_SECRET = "workflowforge-development-jwt-secret-change-before-production-0001"


class AuthSettings(BaseSettings):
    """Validated authentication and session lifecycle settings."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_AUTH_",
        extra="forbid",
        validate_default=True,
    )

    jwt_algorithm: str = "HS256"
    jwt_issuer: str = Field(default="workflowforge", min_length=1)
    jwt_audience: str = Field(default="workflowforge-api", min_length=1)
    jwt_signing_secret: SecretStr = Field(default=SecretStr(DEFAULT_JWT_SIGNING_SECRET))
    access_token_lifetime_seconds: int = Field(default=900, gt=0)
    refresh_token_lifetime_seconds: int = Field(default=2_592_000, gt=0)
    session_lifetime_seconds: int = Field(default=2_592_000, gt=0)
    refresh_token_bytes: int = Field(default=32, ge=32)

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        """Require the single supported JWT algorithm."""

        if value != "HS256":
            msg = "JWT algorithm must be HS256"
            raise ValueError(msg)
        return value

    @field_validator("jwt_signing_secret")
    @classmethod
    def validate_jwt_signing_secret(cls, value: SecretStr) -> SecretStr:
        """Require a strong symmetric signing secret."""

        if len(value.get_secret_value()) < 32:
            msg = "JWT signing secret must be at least 32 characters"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_lifetime_policy(self) -> "AuthSettings":
        """Require refresh-token lifetime not to exceed session lifetime."""

        if self.refresh_token_lifetime_seconds > self.session_lifetime_seconds:
            msg = "Refresh token lifetime must not exceed session lifetime"
            raise ValueError(msg)
        return self


class Settings(BaseSettings):
    """Validated process settings shared by backend packages."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=None,
        extra="forbid",
        validate_default=True,
    )

    app_name: str = "WorkflowForge"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.CONSOLE
    api: ApiSettings = Field(default_factory=lambda: ApiSettings())
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings())
    redis: RedisSettings = Field(default_factory=lambda: RedisSettings())
    s3: S3Settings = Field(default_factory=lambda: S3Settings())
    celery: CelerySettings = Field(default_factory=lambda: CelerySettings())
    scheduler: SchedulerSettings = Field(default_factory=lambda: SchedulerSettings())
    auth: AuthSettings = Field(default_factory=lambda: AuthSettings())

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Parse comma-separated CORS origins from environment variables."""

        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @model_validator(mode="after")
    def validate_production_auth_secret(self) -> "Settings":
        """Prevent the development JWT secret in production."""

        if (
            self.environment is Environment.PRODUCTION
            and self.auth.jwt_signing_secret.get_secret_value() == DEFAULT_JWT_SIGNING_SECRET
        ):
            msg = "Production requires an explicit JWT signing secret"
            raise ValueError(msg)
        return self

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require explicit, printable CORS origins."""

        for origin in value:
            if origin == "*":
                msg = "CORS origins must be explicit"
                raise ValueError(msg)
            if any(character.isspace() or ord(character) < 32 for character in origin):
                msg = "CORS origins must not contain whitespace or control characters"
                raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for process startup code."""

    return Settings()


def _redis_url(settings: RedisSettings, *, db: int) -> str:
    scheme = "rediss" if settings.ssl else "redis"
    password = f":{settings.password.get_secret_value()}@" if settings.password is not None else ""
    return f"{scheme}://{password}{settings.host}:{settings.port}/{db}"

"""WorkflowForge settings foundation."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
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

    model_config = SettingsConfigDict(extra="forbid", validate_default=True)

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
    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings())


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for process startup code."""

    return Settings()

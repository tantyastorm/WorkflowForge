"""WorkflowForge settings foundation."""

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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


class Settings(BaseSettings):
    """Validated process settings shared by backend packages."""

    model_config = SettingsConfigDict(
        env_prefix="WORKFLOWFORGE_",
        env_file=None,
        extra="forbid",
        validate_default=True,
    )

    app_name: str = "WorkflowForge"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.CONSOLE


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for process startup code."""

    return Settings()

"""Alembic migration environment."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from workflowforge_infrastructure.audit import models as audit_models
from workflowforge_infrastructure.config import DatabaseSettings, get_settings
from workflowforge_infrastructure.database.base import metadata
from workflowforge_infrastructure.documents import models as document_models
from workflowforge_infrastructure.identity import models as identity_models

_ = (audit_models, document_models, identity_models)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def database_url() -> str:
    """Return the validated synchronous database URL for Alembic."""

    configured_database = config.attributes.get("database_settings")
    if isinstance(configured_database, DatabaseSettings):
        return configured_database.sync_sqlalchemy_url().render_as_string(hide_password=False)
    return get_settings().database.sync_sqlalchemy_url().render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

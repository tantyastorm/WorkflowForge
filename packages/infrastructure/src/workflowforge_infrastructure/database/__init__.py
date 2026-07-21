"""Database infrastructure helpers."""

from workflowforge_infrastructure.database.base import Base, metadata
from workflowforge_infrastructure.database.engine import (
    create_async_database_engine,
    create_sync_migration_engine,
    dispose_async_engine,
)
from workflowforge_infrastructure.database.errors import (
    DatabaseError,
    DatabaseUnavailableError,
)
from workflowforge_infrastructure.database.health import DatabaseHealthCheck, check_database_health
from workflowforge_infrastructure.database.session import (
    SqlAlchemyTransactionManager,
    async_session_scope,
    create_async_session_factory,
)

__all__ = [
    "Base",
    "DatabaseError",
    "DatabaseHealthCheck",
    "DatabaseUnavailableError",
    "SqlAlchemyTransactionManager",
    "async_session_scope",
    "check_database_health",
    "create_async_database_engine",
    "create_async_session_factory",
    "create_sync_migration_engine",
    "dispose_async_engine",
    "metadata",
]

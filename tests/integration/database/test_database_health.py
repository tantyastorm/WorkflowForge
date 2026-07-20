"""Database health integration tests."""

import pytest
from workflowforge_contracts import DependencyState
from workflowforge_infrastructure.database import (
    check_database_health,
    create_async_database_engine,
    dispose_async_engine,
)

from tests.integration.database.utils import require_postgresql


@pytest.mark.integration
async def test_database_health_check_succeeds() -> None:
    settings = require_postgresql()
    engine = create_async_database_engine(settings)

    try:
        result = await check_database_health(engine)
    finally:
        await dispose_async_engine(engine)

    assert result.name == "postgresql"
    assert result.state is DependencyState.AVAILABLE

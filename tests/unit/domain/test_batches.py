"""Batch domain tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_domain.batches import (
    ArchivedBatchMutationError,
    Batch,
    BatchError,
    BatchId,
    BatchStatus,
)

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER = UUID("11111111-1111-4111-8111-111111111111")
BATCH_ID = BatchId(UUID("22222222-2222-4222-8222-222222222222"))


def test_batch_create_update_archive_lifecycle() -> None:
    batch = Batch.create(
        id=BATCH_ID,
        organization_id=ORG,
        name=" Intake batch ",
        description="Documents",
        external_reference="EXT-1",
        created_by_user_id=USER,
        now=_now(),
    )

    assert batch.name == "Intake batch"
    assert batch.status is BatchStatus.OPEN
    assert batch.lock_version == 1

    updated = batch.update(
        name="Updated",
        description=None,
        external_reference=None,
        actor_user_id=USER,
        now=_now(6),
    )

    assert updated.name == "Updated"
    assert updated.description is None
    assert updated.lock_version == 2
    assert updated.updated_at == _now(6)

    archived = updated.archive(actor_user_id=USER, now=_now(7))

    assert archived.status is BatchStatus.ARCHIVED
    assert archived.archived_by_user_id == USER
    assert archived.lock_version == 3
    with pytest.raises(ArchivedBatchMutationError):
        archived.archive(actor_user_id=USER, now=_now(8))
    with pytest.raises(ArchivedBatchMutationError):
        archived.update(
            name="Nope",
            description=None,
            external_reference=None,
            actor_user_id=USER,
            now=_now(9),
        )


def test_batch_rejects_invalid_text_and_ids() -> None:
    with pytest.raises(BatchError, match="Batch name is required"):
        Batch.create(
            id=BATCH_ID,
            organization_id=ORG,
            name=" ",
            description=None,
            external_reference=None,
            created_by_user_id=USER,
            now=_now(),
        )
    with pytest.raises(BatchError, match="nil UUID"):
        Batch.create(
            id=BATCH_ID,
            organization_id=UUID(int=0),
            name="Name",
            description=None,
            external_reference=None,
            created_by_user_id=USER,
            now=_now(),
        )


def _now(second: int = 5) -> datetime:
    return datetime(2026, 1, 2, 3, 4, second, tzinfo=UTC)

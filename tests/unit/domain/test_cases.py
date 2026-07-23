"""Case domain tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_domain.cases import (
    Case,
    CaseError,
    CaseId,
    CasePriority,
    CaseStatus,
    CaseTask,
    CaseTaskId,
    CaseTaskStatus,
)

ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
USER = UUID("11111111-1111-4111-8111-111111111111")
CASE_ID = CaseId(UUID("22222222-2222-4222-8222-222222222222"))
TASK_ID = CaseTaskId(UUID("33333333-3333-4333-8333-333333333333"))


def test_case_create_update_close_reopen_archive_lifecycle() -> None:
    case = Case.create(
        id=CASE_ID,
        organization_id=ORG,
        title=" Intake case ",
        summary="Summary",
        priority=CasePriority.HIGH,
        external_reference="EXT-1",
        created_by_user_id=USER,
        now=_now(),
    )

    assert case.title == "Intake case"
    assert case.status is CaseStatus.OPEN
    assert case.priority is CasePriority.HIGH

    updated = case.update(
        title="Updated",
        summary=None,
        priority=CasePriority.URGENT,
        external_reference=None,
        actor_user_id=USER,
        now=_now(6),
    )
    closed = updated.close(actor_user_id=USER, now=_now(7))
    reopened = closed.reopen(actor_user_id=USER, now=_now(8))
    archived = reopened.archive(actor_user_id=USER, now=_now(9))

    assert updated.lock_version == 2
    assert closed.status is CaseStatus.CLOSED
    assert closed.closed_by_user_id == USER
    assert reopened.status is CaseStatus.OPEN
    assert archived.status is CaseStatus.ARCHIVED
    assert archived.archived_by_user_id == USER
    rearchived = archived.archive(actor_user_id=USER, now=_now(10))
    assert rearchived.lock_version == archived.lock_version + 1
    with pytest.raises(CaseError):
        archived.update(
            title="Nope",
            summary=None,
            priority=None,
            external_reference=None,
            actor_user_id=USER,
            now=_now(11),
        )


def test_case_task_update_and_complete_lifecycle() -> None:
    task = CaseTask(
        id=TASK_ID,
        organization_id=ORG,
        case_id=CASE_ID,
        title=" Review ",
        description=None,
        status=CaseTaskStatus.OPEN,
        assigned_to_user_id=None,
        due_at=None,
        completed_at=None,
        completed_by_user_id=None,
        created_at=_now(),
        created_by_user_id=USER,
        updated_at=_now(),
        updated_by_user_id=USER,
        lock_version=1,
    )

    updated = task.update(
        title="Review documents",
        description="Read",
        assigned_to_user_id=USER,
        due_at=_now(8),
        actor_user_id=USER,
        now=_now(6),
    )
    completed = updated.complete(actor_user_id=USER, now=_now(7))

    assert updated.title == "Review documents"
    assert updated.assigned_to_user_id == USER
    assert updated.lock_version == 2
    assert completed.status is CaseTaskStatus.COMPLETED
    assert completed.completed_by_user_id == USER
    completed_again = completed.complete(actor_user_id=USER, now=_now(8))
    assert completed_again.lock_version == completed.lock_version + 1


def test_case_rejects_invalid_title_and_closed_reopen_noops() -> None:
    with pytest.raises(CaseError, match="Case title is required"):
        Case.create(
            id=CASE_ID,
            organization_id=ORG,
            title=" ",
            summary=None,
            priority=CasePriority.NORMAL,
            external_reference=None,
            created_by_user_id=USER,
            now=_now(),
        )

    case = Case.create(
        id=CASE_ID,
        organization_id=ORG,
        title="Case",
        summary=None,
        priority=CasePriority.NORMAL,
        external_reference=None,
        created_by_user_id=USER,
        now=_now(),
    )

    reopened = case.reopen(actor_user_id=USER, now=_now(6))
    assert reopened.status is CaseStatus.OPEN
    assert reopened.lock_version == case.lock_version + 1


def _now(second: int = 5) -> datetime:
    return datetime(2026, 1, 2, 3, 4, second, tzinfo=UTC)

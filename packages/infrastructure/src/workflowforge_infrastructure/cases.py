"""Case persistence adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from workflowforge_application.cases import CaseListFilter, CaseListPage
from workflowforge_application.documents import DocumentNotFoundError
from workflowforge_domain.cases import (
    Case,
    CaseComment,
    CaseCommentId,
    CaseDecision,
    CaseDecisionId,
    CaseDocument,
    CaseDocumentId,
    CaseId,
    CasePriority,
    CaseStatus,
    CaseTask,
    CaseTaskId,
    CaseTaskStatus,
)
from workflowforge_domain.documents import DocumentId

from workflowforge_infrastructure.database.base import Base


class CaseRecord(Base):
    """Case ORM record."""

    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed', 'archived')", name="status_valid"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="priority_valid"),
        CheckConstraint("lock_version > 0", name="lock_version_positive"),
        UniqueConstraint("organization_id", "id", name="uq_cases_organization_id_id"),
        Index("ix_cases_organization_status", "organization_id", "status"),
        Index("ix_cases_organization_priority", "organization_id", "priority"),
        Index("ix_cases_organization_created_at", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class CaseDocumentRecord(Base):
    """Case document membership ORM record."""

    __tablename__ = "case_documents"
    __table_args__ = (
        UniqueConstraint("case_id", "document_id", name="uq_case_documents_case_document"),
        ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_documents_organization_case_cases",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_case_documents_organization_document_documents",
            ondelete="CASCADE",
        ),
        Index("ix_case_documents_organization_case", "organization_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    added_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class CaseCommentRecord(Base):
    """Case comment ORM record."""

    __tablename__ = "case_comments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_comments_organization_case_cases",
            ondelete="CASCADE",
        ),
        Index("ix_case_comments_organization_case", "organization_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CaseTaskRecord(Base):
    """Case task ORM record."""

    __tablename__ = "case_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'completed', 'cancelled')", name="status_valid"),
        CheckConstraint("lock_version > 0", name="lock_version_positive"),
        ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_tasks_organization_case_cases",
            ondelete="CASCADE",
        ),
        Index("ix_case_tasks_organization_case", "organization_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False)


class CaseDecisionRecord(Base):
    """Case decision ORM record."""

    __tablename__ = "case_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "case_id"],
            ["cases.organization_id", "cases.id"],
            name="fk_case_decisions_organization_case_cases",
            ondelete="CASCADE",
        ),
        Index("ix_case_decisions_organization_case", "organization_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    case_id: Mapped[UUID] = mapped_column(nullable=False)
    decision_type: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class SqlAlchemyCaseRepository:
    """SQLAlchemy implementation of case repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, case: Case) -> Case:
        record = _case_record(case)
        self._session.add(record)
        await self._session.flush()
        return _case(record)

    async def get(self, *, organization_id: UUID, case_id: CaseId) -> Case | None:
        record = await self._record(organization_id=organization_id, case_id=case_id)
        return _case(record) if record else None

    async def get_for_update(self, *, organization_id: UUID, case_id: CaseId) -> Case | None:
        result = await self._session.execute(
            select(CaseRecord)
            .where(CaseRecord.organization_id == organization_id, CaseRecord.id == case_id.value)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        return _case(record) if record else None

    async def list_cases(self, *, organization_id: UUID, query: CaseListFilter) -> CaseListPage:
        statement = select(CaseRecord).where(CaseRecord.organization_id == organization_id)
        if query.status is not None:
            statement = statement.where(CaseRecord.status == query.status.value)
        elif query.archived is True:
            statement = statement.where(CaseRecord.status == CaseStatus.ARCHIVED.value)
        elif query.archived is False:
            statement = statement.where(CaseRecord.status != CaseStatus.ARCHIVED.value)
        if query.priority is not None:
            statement = statement.where(CaseRecord.priority == query.priority.value)
        if query.title is not None:
            statement = statement.where(CaseRecord.title.ilike(f"%{query.title}%"))
        total_result = await self._session.execute(
            select(func.count()).select_from(statement.subquery())
        )
        result = await self._session.execute(
            statement.order_by(CaseRecord.created_at.desc(), CaseRecord.id.desc())
            .limit(query.limit)
            .offset(query.offset)
        )
        return CaseListPage(
            items=[_case(record) for record in result.scalars()],
            total=int(total_result.scalar_one()),
            limit=query.limit,
            offset=query.offset,
        )

    async def update(self, case: Case) -> Case:
        await self._session.execute(
            update(CaseRecord)
            .where(
                CaseRecord.organization_id == case.organization_id,
                CaseRecord.id == case.id.value,
                CaseRecord.lock_version == case.lock_version - 1,
            )
            .values(
                title=case.title,
                summary=case.summary,
                status=case.status.value,
                priority=case.priority.value,
                external_reference=case.external_reference,
                updated_at=case.updated_at,
                updated_by_user_id=case.updated_by_user_id,
                closed_at=case.closed_at,
                closed_by_user_id=case.closed_by_user_id,
                archived_at=case.archived_at,
                archived_by_user_id=case.archived_by_user_id,
                lock_version=case.lock_version,
            )
        )
        await self._session.flush()
        return case

    async def add_document(self, membership: CaseDocument) -> CaseDocument:
        record = CaseDocumentRecord(
            id=membership.id.value,
            organization_id=membership.organization_id,
            case_id=membership.case_id.value,
            document_id=membership.document_id.value,
            added_at=membership.added_at,
            added_by_user_id=membership.added_by_user_id,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            existing = await self._membership(
                organization_id=membership.organization_id,
                case_id=membership.case_id,
                document_id=membership.document_id,
            )
            if existing is not None:
                return _case_document(existing)
            raise DocumentNotFoundError("Document was not found.") from exc
        return _case_document(record)

    async def remove_document(
        self,
        *,
        organization_id: UUID,
        case_id: CaseId,
        document_id: DocumentId,
    ) -> bool:
        result = await self._session.execute(
            delete(CaseDocumentRecord).where(
                CaseDocumentRecord.organization_id == organization_id,
                CaseDocumentRecord.case_id == case_id.value,
                CaseDocumentRecord.document_id == document_id.value,
            )
        )
        await self._session.flush()
        return bool(cast("Any", result).rowcount)

    async def list_documents(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseDocument]:
        result = await self._session.execute(
            select(CaseDocumentRecord).where(
                CaseDocumentRecord.organization_id == organization_id,
                CaseDocumentRecord.case_id == case_id.value,
            )
        )
        return [_case_document(record) for record in result.scalars()]

    async def add_comment(self, comment: CaseComment) -> CaseComment:
        record = CaseCommentRecord(
            id=comment.id.value,
            organization_id=comment.organization_id,
            case_id=comment.case_id.value,
            body=comment.body,
            created_at=comment.created_at,
            created_by_user_id=comment.created_by_user_id,
            updated_at=comment.updated_at,
            updated_by_user_id=comment.updated_by_user_id,
        )
        self._session.add(record)
        await self._session.flush()
        return _comment(record)

    async def list_comments(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseComment]:
        result = await self._session.execute(
            select(CaseCommentRecord).where(
                CaseCommentRecord.organization_id == organization_id,
                CaseCommentRecord.case_id == case_id.value,
            )
        )
        return [_comment(record) for record in result.scalars()]

    async def add_task(self, task: CaseTask) -> CaseTask:
        record = CaseTaskRecord(
            id=task.id.value,
            organization_id=task.organization_id,
            case_id=task.case_id.value,
            title=task.title,
            description=task.description,
            status=task.status.value,
            assigned_to_user_id=task.assigned_to_user_id,
            due_at=task.due_at,
            completed_at=task.completed_at,
            completed_by_user_id=task.completed_by_user_id,
            created_at=task.created_at,
            created_by_user_id=task.created_by_user_id,
            updated_at=task.updated_at,
            updated_by_user_id=task.updated_by_user_id,
            lock_version=task.lock_version,
        )
        self._session.add(record)
        await self._session.flush()
        return _task(record)

    async def get_task_for_update(
        self,
        *,
        organization_id: UUID,
        case_id: CaseId,
        task_id: CaseTaskId,
    ) -> CaseTask | None:
        result = await self._session.execute(
            select(CaseTaskRecord)
            .where(
                CaseTaskRecord.organization_id == organization_id,
                CaseTaskRecord.case_id == case_id.value,
                CaseTaskRecord.id == task_id.value,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        return _task(record) if record else None

    async def update_task(self, task: CaseTask) -> CaseTask:
        await self._session.execute(
            update(CaseTaskRecord)
            .where(
                CaseTaskRecord.organization_id == task.organization_id,
                CaseTaskRecord.case_id == task.case_id.value,
                CaseTaskRecord.id == task.id.value,
                CaseTaskRecord.lock_version == task.lock_version - 1,
            )
            .values(
                title=task.title,
                description=task.description,
                status=task.status.value,
                assigned_to_user_id=task.assigned_to_user_id,
                due_at=task.due_at,
                completed_at=task.completed_at,
                completed_by_user_id=task.completed_by_user_id,
                updated_at=task.updated_at,
                updated_by_user_id=task.updated_by_user_id,
                lock_version=task.lock_version,
            )
        )
        await self._session.flush()
        return task

    async def list_tasks(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseTask]:
        result = await self._session.execute(
            select(CaseTaskRecord).where(
                CaseTaskRecord.organization_id == organization_id,
                CaseTaskRecord.case_id == case_id.value,
            )
        )
        return [_task(record) for record in result.scalars()]

    async def add_decision(self, decision: CaseDecision) -> CaseDecision:
        record = CaseDecisionRecord(
            id=decision.id.value,
            organization_id=decision.organization_id,
            case_id=decision.case_id.value,
            decision_type=decision.decision_type,
            rationale=decision.rationale,
            created_at=decision.created_at,
            created_by_user_id=decision.created_by_user_id,
        )
        self._session.add(record)
        await self._session.flush()
        return _decision(record)

    async def list_decisions(self, *, organization_id: UUID, case_id: CaseId) -> list[CaseDecision]:
        result = await self._session.execute(
            select(CaseDecisionRecord).where(
                CaseDecisionRecord.organization_id == organization_id,
                CaseDecisionRecord.case_id == case_id.value,
            )
        )
        return [_decision(record) for record in result.scalars()]

    async def _record(self, *, organization_id: UUID, case_id: CaseId) -> CaseRecord | None:
        result = await self._session.execute(
            select(CaseRecord).where(
                CaseRecord.organization_id == organization_id,
                CaseRecord.id == case_id.value,
            )
        )
        return result.scalar_one_or_none()

    async def _membership(
        self,
        *,
        organization_id: UUID,
        case_id: CaseId,
        document_id: DocumentId,
    ) -> CaseDocumentRecord | None:
        result = await self._session.execute(
            select(CaseDocumentRecord).where(
                CaseDocumentRecord.organization_id == organization_id,
                CaseDocumentRecord.case_id == case_id.value,
                CaseDocumentRecord.document_id == document_id.value,
            )
        )
        return result.scalar_one_or_none()


def _case_record(case: Case) -> CaseRecord:
    return CaseRecord(
        id=case.id.value,
        organization_id=case.organization_id,
        title=case.title,
        summary=case.summary,
        status=case.status.value,
        priority=case.priority.value,
        external_reference=case.external_reference,
        created_at=case.created_at,
        created_by_user_id=case.created_by_user_id,
        updated_at=case.updated_at,
        updated_by_user_id=case.updated_by_user_id,
        closed_at=case.closed_at,
        closed_by_user_id=case.closed_by_user_id,
        archived_at=case.archived_at,
        archived_by_user_id=case.archived_by_user_id,
        lock_version=case.lock_version,
    )


def _case(record: CaseRecord) -> Case:
    return Case(
        id=CaseId(record.id),
        organization_id=record.organization_id,
        title=record.title,
        summary=record.summary,
        status=CaseStatus(record.status),
        priority=CasePriority(record.priority),
        external_reference=record.external_reference,
        created_at=record.created_at.astimezone(UTC),
        created_by_user_id=record.created_by_user_id,
        updated_at=record.updated_at.astimezone(UTC),
        updated_by_user_id=record.updated_by_user_id,
        closed_at=record.closed_at.astimezone(UTC) if record.closed_at else None,
        closed_by_user_id=record.closed_by_user_id,
        archived_at=record.archived_at.astimezone(UTC) if record.archived_at else None,
        archived_by_user_id=record.archived_by_user_id,
        lock_version=record.lock_version,
    )


def _case_document(record: CaseDocumentRecord) -> CaseDocument:
    return CaseDocument(
        CaseDocumentId(record.id),
        record.organization_id,
        CaseId(record.case_id),
        DocumentId(record.document_id),
        record.added_at.astimezone(UTC),
        record.added_by_user_id,
    )


def _comment(record: CaseCommentRecord) -> CaseComment:
    return CaseComment(
        CaseCommentId(record.id),
        record.organization_id,
        CaseId(record.case_id),
        record.body,
        record.created_at.astimezone(UTC),
        record.created_by_user_id,
        record.updated_at.astimezone(UTC) if record.updated_at else None,
        record.updated_by_user_id,
    )


def _task(record: CaseTaskRecord) -> CaseTask:
    return CaseTask(
        CaseTaskId(record.id),
        record.organization_id,
        CaseId(record.case_id),
        record.title,
        record.description,
        CaseTaskStatus(record.status),
        record.assigned_to_user_id,
        record.due_at.astimezone(UTC) if record.due_at else None,
        record.completed_at.astimezone(UTC) if record.completed_at else None,
        record.completed_by_user_id,
        record.created_at.astimezone(UTC),
        record.created_by_user_id,
        record.updated_at.astimezone(UTC),
        record.updated_by_user_id,
        record.lock_version,
    )


def _decision(record: CaseDecisionRecord) -> CaseDecision:
    return CaseDecision(
        CaseDecisionId(record.id),
        record.organization_id,
        CaseId(record.case_id),
        record.decision_type,
        record.rationale,
        record.created_at.astimezone(UTC),
        record.created_by_user_id,
    )

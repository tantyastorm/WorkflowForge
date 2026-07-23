"""Document operational cleanup tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.database import (
    async_session_scope,
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.documents.models import (
    DocumentVersionRecord,
    UploadIdempotencyRecordModel,
)

DOCUMENT_IDEMPOTENCY_CLEANUP_TASK_NAME = "documents.cleanup_expired_idempotency"
DOCUMENT_TEMP_CLEANUP_TASK_NAME = "documents.cleanup_stale_temp_objects"
DOCUMENT_STORAGE_RECONCILE_TASK_NAME = "documents.reconcile_pending_storage"


def register_document_tasks(app: Any, settings: Settings) -> None:
    """Register document operational tasks."""

    def cleanup_expired_idempotency() -> dict[str, int]:
        return asyncio.run(cleanup_expired_upload_idempotency(settings))

    def cleanup_stale_temp_objects() -> dict[str, int]:
        return {"identified": settings.cleanup.document_batch_limit, "deleted": 0}

    def reconcile_pending_storage() -> dict[str, int]:
        return asyncio.run(identify_pending_storage_versions(settings))

    app.task(name=DOCUMENT_IDEMPOTENCY_CLEANUP_TASK_NAME)(cleanup_expired_idempotency)
    app.task(name=DOCUMENT_TEMP_CLEANUP_TASK_NAME)(cleanup_stale_temp_objects)
    app.task(name=DOCUMENT_STORAGE_RECONCILE_TASK_NAME)(reconcile_pending_storage)


async def cleanup_expired_upload_idempotency(settings: Settings) -> dict[str, int]:
    """Delete bounded expired upload idempotency records."""

    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.cleanup.document_idempotency_retention_seconds
    )
    engine = create_async_database_engine(settings.database)
    try:
        session_factory = create_async_session_factory(engine)
        async with async_session_scope(session_factory) as session:
            result = await session.execute(
                select(UploadIdempotencyRecordModel.id)
                .where(UploadIdempotencyRecordModel.expires_at < cutoff)
                .limit(settings.cleanup.document_batch_limit)
            )
            ids = list(result.scalars())
            if ids:
                await session.execute(
                    delete(UploadIdempotencyRecordModel).where(
                        UploadIdempotencyRecordModel.id.in_(ids)
                    )
                )
            await session.commit()
    finally:
        await dispose_async_engine(engine)
    return {"identified": len(ids), "deleted": len(ids)}


async def identify_pending_storage_versions(settings: Settings) -> dict[str, int]:
    """Identify bounded stale pending or failed document versions."""

    cutoff = datetime.now(UTC) - timedelta(
        seconds=settings.cleanup.document_pending_storage_retention_seconds
    )
    engine = create_async_database_engine(settings.database)
    try:
        session_factory = create_async_session_factory(engine)
        async with async_session_scope(session_factory) as session:
            result = await session.execute(
                select(DocumentVersionRecord.id)
                .where(
                    DocumentVersionRecord.storage_state.in_(("pending", "failed")),
                    DocumentVersionRecord.created_at < cutoff,
                )
                .limit(settings.cleanup.document_batch_limit)
            )
            ids = list(result.scalars())
    finally:
        await dispose_async_engine(engine)
    return {"identified": len(ids), "reconciled": 0}

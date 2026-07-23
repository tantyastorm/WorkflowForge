"""Phase 3 API route mapping tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workflowforge_api.dependencies import (
    get_batch_service,
    get_case_service,
    get_current_principal,
    get_document_service,
    get_independent_audit_recorder,
    get_object_storage,
    get_resolve_tenant_context,
)
from workflowforge_api.factory import create_app
from workflowforge_application.authorization import ResolveTenantContextCommand, TenantContext
from workflowforge_application.batches import BatchListFilter, BatchListPage, BatchNotFoundError
from workflowforge_application.cases import CaseListFilter, CaseListPage, CaseNotFoundError
from workflowforge_application.documents import (
    ConcurrencyConflictError,
    DocumentListFilter,
    DocumentListPage,
    DocumentNotFoundError,
    DocumentProjection,
    DownloadUrl,
)
from workflowforge_application.identity import VerifiedAccessPrincipal
from workflowforge_domain.audit import AuditEvent
from workflowforge_domain.batches import Batch, BatchDocument, BatchDocumentId, BatchId
from workflowforge_domain.cases import Case, CaseId, CasePriority
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentArtifact,
    DocumentArtifactId,
    DocumentArtifactType,
    DocumentId,
    DocumentSourceType,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
    StorageObjectKey,
)
from workflowforge_domain.identity import Role, SessionId
from workflowforge_infrastructure.config import Environment, Settings

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("77777777-7777-4777-8777-777777777777")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
DOCUMENT_ID = UUID("55555555-5555-4555-8555-555555555555")
VERSION_ID = UUID("66666666-6666-4666-8666-666666666666")
BATCH_ID = UUID("88888888-8888-4888-8888-888888888888")
CASE_ID = UUID("99999999-9999-4999-8999-999999999999")


def test_document_metadata_archive_and_download_routes() -> None:
    app = _app(documents=FakeDocumentService())

    with TestClient(app) as client:
        listed = client.get(f"/api/v1/organizations/{ORG_ID}/documents")
        detail = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}")
        archived = client.post(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/archive",
            json={"lock_version": 1},
        )
        download = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/download")

    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == str(DOCUMENT_ID)
    assert detail.json()["current_version"]["id"] == str(VERSION_ID)
    assert archived.json()["status"] == "archived"
    assert download.json()["url"] == "https://storage.example/download"


def test_document_version_and_artifact_routes() -> None:
    app = _app(documents=FakeDocumentService())

    with TestClient(app) as client:
        versions = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/versions")
        version = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/versions/{VERSION_ID}"
        )
        artifacts = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/artifacts")
        artifact = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/artifacts/{VERSION_ID}"
        )
        artifact_download = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/artifacts/{VERSION_ID}/download"
        )
        version_download = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/versions/{VERSION_ID}/download"
        )

    assert versions.json()["items"][0]["id"] == str(VERSION_ID)
    assert version.json()["version_number"] == 1
    assert artifacts.json()["items"][0]["artifact_type"] == "text"
    assert artifact.json()["media_type"] == "text/plain"
    assert artifact_download.json()["filename"] == "report.pdf"
    assert version_download.json()["byte_size"] == 9


def test_document_archive_conflict_maps_to_409() -> None:
    app = _app(documents=FakeDocumentService(conflict=True))

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/archive",
            json={"lock_version": 99},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "concurrency_conflict"


def test_document_route_not_found_mappings_are_stable() -> None:
    app = _app(documents=FakeDocumentService(not_found=True))

    with TestClient(app) as client:
        detail = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}")
        versions = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/versions")
        version = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/versions/{VERSION_ID}"
        )
        artifacts = client.get(f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/artifacts")
        artifact = client.get(
            f"/api/v1/organizations/{ORG_ID}/documents/{DOCUMENT_ID}/artifacts/{VERSION_ID}"
        )

    assert detail.status_code == 404
    assert versions.status_code == 404
    assert version.status_code == 404
    assert artifacts.status_code == 404
    assert artifact.status_code == 404


def test_batch_routes_create_add_list_and_archive() -> None:
    app = _app(batches=FakeBatchService())

    with TestClient(app) as client:
        created = client.post(f"/api/v1/organizations/{ORG_ID}/batches", json={"name": "Batch"})
        listed = client.get(f"/api/v1/organizations/{ORG_ID}/batches")
        membership = client.post(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}/documents",
            json={"document_id": str(DOCUMENT_ID)},
        )
        archived = client.post(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}/archive",
            json={"lock_version": 1},
        )

    assert created.status_code == 201
    assert listed.json()["items"][0]["name"] == "Batch"
    assert membership.json()["document_id"] == str(DOCUMENT_ID)
    assert archived.json()["status"] == "archived"


def test_batch_routes_get_update_list_documents_and_remove() -> None:
    app = _app(batches=FakeBatchService())

    with TestClient(app) as client:
        got = client.get(f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}")
        updated = client.patch(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}",
            json={"lock_version": 1, "name": "Updated"},
        )
        documents = client.get(f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}/documents")
        removed = client.delete(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}/documents/{DOCUMENT_ID}"
        )

    assert got.json()["id"] == str(BATCH_ID)
    assert updated.json()["name"] == "Updated"
    assert documents.json()["items"][0]["document_id"] == str(DOCUMENT_ID)
    assert removed.status_code == 204


def test_batch_route_errors_map_to_stable_status_codes() -> None:
    app = _app(batches=FakeBatchService(not_found=True, conflict=True))

    with TestClient(app) as client:
        missing = client.get(f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}")
        conflict = client.patch(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}",
            json={"lock_version": 99, "name": "Updated"},
        )
        archive_conflict = client.post(
            f"/api/v1/organizations/{ORG_ID}/batches/{BATCH_ID}/archive",
            json={"lock_version": 99},
        )

    assert missing.status_code == 404
    assert conflict.status_code == 409
    assert archive_conflict.status_code == 409


def test_case_routes_create_detail_comment_task_decision_and_state() -> None:
    app = _app(cases=FakeCaseService())

    with TestClient(app) as client:
        created = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases",
            json={"title": "Case", "priority": "normal"},
        )
        detail = client.get(f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}")
        comment = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/comments",
            json={"body": "Ready"},
        )
        task = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/tasks",
            json={"title": "Review"},
        )
        decision = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/decisions",
            json={"decision_type": "accept", "rationale": "Complete"},
        )
        closed = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/close",
            json={"lock_version": 1},
        )

    assert created.status_code == 201
    assert detail.json()["case"]["id"] == str(CASE_ID)
    assert comment.json()["body"] == "Ready"
    assert task.json()["title"] == "Review"
    assert decision.json()["decision_type"] == "accept"
    assert closed.json()["status"] == "closed"


def test_case_routes_update_documents_tasks_and_archive() -> None:
    app = _app(cases=FakeCaseService())
    task_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    with TestClient(app) as client:
        listed = client.get(f"/api/v1/organizations/{ORG_ID}/cases")
        updated = client.patch(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}",
            json={"lock_version": 1, "title": "Updated"},
        )
        document = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/documents",
            json={"document_id": str(DOCUMENT_ID)},
        )
        removed = client.delete(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/documents/{DOCUMENT_ID}"
        )
        changed_task = client.patch(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/tasks/{task_id}",
            json={"lock_version": 1, "title": "Updated task"},
        )
        completed_task = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/tasks/{task_id}/complete",
            json={"lock_version": 1},
        )
        reopened = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/reopen",
            json={"lock_version": 1},
        )
        archived = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/archive",
            json={"lock_version": 1},
        )

    assert listed.json()["items"][0]["id"] == str(CASE_ID)
    assert updated.json()["title"] == "Updated"
    assert document.json()["document_id"] == str(DOCUMENT_ID)
    assert removed.status_code == 204
    assert changed_task.json()["title"] == "Updated task"
    assert completed_task.json()["status"] == "completed"
    assert reopened.json()["status"] == "open"
    assert archived.json()["status"] == "archived"


def test_case_route_errors_map_to_stable_status_codes() -> None:
    app = _app(cases=FakeCaseService(not_found=True, conflict=True))

    with TestClient(app) as client:
        missing = client.get(f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}")
        conflict = client.patch(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}",
            json={"lock_version": 99, "title": "Updated"},
        )
        task_conflict = client.patch(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/tasks/{CASE_ID}",
            json={"lock_version": 99, "title": "Updated task"},
        )
        close_conflict = client.post(
            f"/api/v1/organizations/{ORG_ID}/cases/{CASE_ID}/close",
            json={"lock_version": 99},
        )

    assert missing.status_code == 404
    assert conflict.status_code == 409
    assert task_conflict.status_code == 409
    assert close_conflict.status_code == 409


def _app(
    *,
    documents: FakeDocumentService | None = None,
    batches: FakeBatchService | None = None,
    cases: FakeCaseService | None = None,
) -> FastAPI:
    app = create_app(Settings(environment=Environment.TEST))
    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_resolve_tenant_context] = lambda: FakeResolveTenantContext()
    app.dependency_overrides[get_independent_audit_recorder] = NullAuditRecorder
    app.dependency_overrides[get_document_service] = lambda: documents or FakeDocumentService()
    app.dependency_overrides[get_object_storage] = lambda: FakeStorage()
    app.dependency_overrides[get_batch_service] = lambda: batches or FakeBatchService()
    app.dependency_overrides[get_case_service] = lambda: cases or FakeCaseService()
    return app


class FakeDocumentService:
    def __init__(self, *, conflict: bool = False, not_found: bool = False) -> None:
        self._conflict = conflict
        self._not_found = not_found

    async def list_documents(
        self, *, tenant: TenantContext, query: DocumentListFilter | None = None
    ) -> DocumentListPage:
        _ = tenant
        limit = 25 if query is None else query.limit
        offset = 0 if query is None else query.offset
        document = _document()
        version = _version()
        return DocumentListPage(
            items=[
                DocumentProjection(
                    id=document.id,
                    organization_id=document.organization_id,
                    display_filename=document.display_filename,
                    source_type=document.source_type,
                    status=document.status,
                    current_version_id=document.current_version_id,
                    media_type=version.media_type,
                    byte_size=version.byte_size,
                    storage_state=version.storage_state.value,
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                    lock_version=document.lock_version,
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )

    async def get_document(self, document_id: DocumentId, *, tenant: TenantContext) -> Document:
        _ = (document_id, tenant)
        if self._not_found:
            raise DocumentNotFoundError("missing")
        return _document()

    async def get_version(
        self,
        *,
        tenant: TenantContext,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        _ = (tenant, document_id, version_id)
        if self._not_found:
            raise DocumentNotFoundError("missing")
        return _version()

    async def list_versions(
        self,
        document_id: DocumentId,
        *,
        tenant: TenantContext,
    ) -> list[DocumentVersion]:
        _ = (document_id, tenant)
        if self._not_found:
            raise DocumentNotFoundError("missing")
        return [_version()]

    async def list_artifacts(
        self,
        document_id: DocumentId,
        *,
        tenant: TenantContext,
    ) -> list[DocumentArtifact]:
        _ = (document_id, tenant)
        if self._not_found:
            raise DocumentNotFoundError("missing")
        return [_artifact()]

    async def get_artifact(
        self,
        *,
        tenant: TenantContext,
        document_id: DocumentId,
        artifact_id: DocumentArtifactId,
    ) -> DocumentArtifact:
        _ = (tenant, document_id, artifact_id)
        if self._not_found:
            raise DocumentNotFoundError("missing")
        return _artifact()

    async def archive_document_with_lock(self, command: Any, *, tenant: TenantContext) -> Document:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        return _document().archive(actor_user_id=USER_ID, now=NOW)

    async def create_download_url(
        self, command: Any, *, tenant: TenantContext, storage: Any
    ) -> Any:
        _ = (command, tenant, storage)
        return type(
            "Download",
            (),
            {
                "url": "https://storage.example/download",
                "expires_at": NOW + timedelta(minutes=1),
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "byte_size": 9,
            },
        )()


class FakeBatchService:
    def __init__(self, *, not_found: bool = False, conflict: bool = False) -> None:
        self._not_found = not_found
        self._conflict = conflict

    async def list_batches(self, *, tenant: TenantContext, query: BatchListFilter) -> BatchListPage:
        _ = tenant
        return BatchListPage(items=[_batch()], total=1, limit=query.limit, offset=query.offset)

    async def create(self, command: Any, *, tenant: TenantContext) -> Batch:
        _ = (command, tenant)
        return _batch()

    async def get(self, batch_id: BatchId, *, tenant: TenantContext) -> Batch:
        _ = (batch_id, tenant)
        if self._not_found:
            raise BatchNotFoundError("missing")
        return _batch()

    async def update(self, command: Any, *, tenant: TenantContext) -> Batch:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        return _batch(name="Updated")

    async def add_document(self, command: Any, *, tenant: TenantContext) -> BatchDocument:
        _ = (command, tenant)
        return _batch_document()

    async def remove_document(self, command: Any, *, tenant: TenantContext) -> bool:
        _ = (command, tenant)
        return True

    async def list_documents(
        self,
        batch_id: BatchId,
        *,
        tenant: TenantContext,
    ) -> list[BatchDocument]:
        _ = (batch_id, tenant)
        return [_batch_document()]

    async def archive(self, command: Any, *, tenant: TenantContext) -> Batch:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        return _batch().archive(actor_user_id=USER_ID, now=NOW)


class FakeCaseService:
    def __init__(self, *, not_found: bool = False, conflict: bool = False) -> None:
        self._not_found = not_found
        self._conflict = conflict

    async def list_cases(self, *, tenant: TenantContext, query: CaseListFilter) -> CaseListPage:
        _ = tenant
        return CaseListPage(items=[_case()], total=1, limit=query.limit, offset=query.offset)

    async def create(self, command: Any, *, tenant: TenantContext) -> Case:
        _ = (command, tenant)
        return _case()

    async def update(self, command: Any, *, tenant: TenantContext) -> Case:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        return _case(title="Updated")

    async def get(self, case_id: CaseId, *, tenant: TenantContext) -> Case:
        _ = (case_id, tenant)
        if self._not_found:
            raise CaseNotFoundError("missing")
        return _case()

    async def details(self, case_id: CaseId, *, tenant: TenantContext) -> tuple[list[Any], ...]:
        _ = (case_id, tenant)
        return ([], [], [], [])

    async def add_document(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        return _case_document()

    async def remove_document(self, command: Any, *, tenant: TenantContext) -> bool:
        _ = (command, tenant)
        return True

    async def create_comment(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        return type(
            "Comment",
            (),
            {
                "id": CaseId(CASE_ID),
                "case_id": CaseId(CASE_ID),
                "body": "Ready",
                "created_at": NOW,
                "created_by_user_id": USER_ID,
            },
        )()

    async def create_task(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        task_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        return type(
            "Task",
            (),
            {
                "id": type("TaskId", (), {"value": task_id})(),
                "case_id": CaseId(CASE_ID),
                "title": "Review",
                "description": None,
                "status": type("Status", (), {"value": "open"})(),
                "assigned_to_user_id": None,
                "due_at": None,
                "completed_at": None,
                "lock_version": 1,
            },
        )()

    async def update_task(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        task = await self.create_task(command, tenant=tenant)
        task.title = "Updated task"
        return task

    async def complete_task(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        task = await self.create_task(command, tenant=tenant)
        task.status = type("Status", (), {"value": "completed"})()
        task.completed_at = NOW
        return task

    async def create_decision(self, command: Any, *, tenant: TenantContext) -> Any:
        _ = (command, tenant)
        decision_id = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        return type(
            "Decision",
            (),
            {
                "id": type("DecisionId", (), {"value": decision_id})(),
                "case_id": CaseId(CASE_ID),
                "decision_type": "accept",
                "rationale": "Complete",
                "created_at": NOW,
                "created_by_user_id": USER_ID,
            },
        )()

    async def close(self, command: Any, *, tenant: TenantContext) -> Case:
        _ = (command, tenant)
        if self._conflict:
            raise ConcurrencyConflictError("changed")
        return _case().close(actor_user_id=USER_ID, now=NOW)

    async def reopen(self, command: Any, *, tenant: TenantContext) -> Case:
        _ = (command, tenant)
        return _case()

    async def archive(self, command: Any, *, tenant: TenantContext) -> Case:
        _ = (command, tenant)
        return _case().archive(actor_user_id=USER_ID, now=NOW)


class FakeStorage:
    async def create_download_url(
        self, *, key: StorageObjectKey, expires_in_seconds: int, now: datetime
    ) -> DownloadUrl:
        _ = (key, expires_in_seconds)
        return DownloadUrl(url="https://storage.example/download", expires_at=now)


class FakeResolveTenantContext:
    async def __call__(self, command: ResolveTenantContextCommand) -> TenantContext:
        assert command.organization_id == ORG_ID
        return TenantContext.create(
            user_id=USER_ID,
            organization_id=ORG_ID,
            membership_id=MEMBERSHIP_ID,
            role=Role.ADMIN,
        )


class NullAuditRecorder:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


def _principal() -> VerifiedAccessPrincipal:
    return VerifiedAccessPrincipal(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=TOKEN_ID,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _document() -> Document:
    return Document.register(
        id=DocumentId(DOCUMENT_ID),
        organization_id=ORG_ID,
        display_filename="report.pdf",
        source_type=DocumentSourceType.UPLOAD,
        source_reference=None,
        current_version=_version(),
        created_by_user_id=USER_ID,
        now=NOW,
    ).mark_stored(actor_user_id=USER_ID, now=NOW)


def _version() -> DocumentVersion:
    return DocumentVersion.create(
        id=DocumentVersionId(VERSION_ID),
        organization_id=ORG_ID,
        document_id=DocumentId(DOCUMENT_ID),
        version_number=1,
        original_filename="report.pdf",
        media_type="application/pdf",
        byte_size=9,
        content_hash=ContentHash("a" * 64),
        storage_state=DocumentStorageState.STORED,
        created_at=NOW,
        created_by_user_id=USER_ID,
    )


def _batch(*, name: str = "Batch") -> Batch:
    return Batch.create(
        id=BatchId(BATCH_ID),
        organization_id=ORG_ID,
        name=name,
        description=None,
        external_reference=None,
        created_by_user_id=USER_ID,
        now=NOW,
    )


def _batch_document() -> BatchDocument:
    return BatchDocument(
        id=BatchDocumentId(UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")),
        organization_id=ORG_ID,
        batch_id=BatchId(BATCH_ID),
        document_id=DocumentId(DOCUMENT_ID),
        added_at=NOW,
        added_by_user_id=USER_ID,
    )


def _case(*, title: str = "Case") -> Case:
    return Case.create(
        id=CaseId(CASE_ID),
        organization_id=ORG_ID,
        title=title,
        summary=None,
        priority=CasePriority.NORMAL,
        external_reference=None,
        created_by_user_id=USER_ID,
        now=NOW,
    )


def _artifact() -> DocumentArtifact:
    return DocumentArtifact.create(
        id=DocumentArtifactId(VERSION_ID),
        organization_id=ORG_ID,
        document_id=DocumentId(DOCUMENT_ID),
        document_version_id=DocumentVersionId(VERSION_ID),
        artifact_type=DocumentArtifactType.TEXT,
        media_type="text/plain",
        byte_size=12,
        content_hash=ContentHash("b" * 64),
        storage_object_key=StorageObjectKey(
            f"artifacts/{ORG_ID}/{DOCUMENT_ID}/{VERSION_ID}/text/demo.txt"
        ),
        metadata={"lang": "en"},
        created_at=NOW,
        created_by_user_id=USER_ID,
    )


def _case_document() -> Any:
    return type(
        "CaseDocument",
        (),
        {
            "id": type(
                "CaseDocumentId",
                (),
                {"value": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")},
            )(),
            "case_id": CaseId(CASE_ID),
            "document_id": DocumentId(DOCUMENT_ID),
            "added_at": NOW,
            "added_by_user_id": USER_ID,
        },
    )()

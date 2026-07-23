"""Document upload API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workflowforge_api.dependencies import (
    get_current_principal,
    get_independent_audit_recorder,
    get_resolve_tenant_context,
    get_upload_document,
)
from workflowforge_api.factory import create_app
from workflowforge_application.authorization import ResolveTenantContextCommand, TenantContext
from workflowforge_application.documents import (
    IdempotencyConflictError,
    UploadDocumentCommand,
    UploadDocumentOutcome,
    UploadDocumentResult,
)
from workflowforge_application.identity import VerifiedAccessPrincipal
from workflowforge_domain.audit import AuditEvent
from workflowforge_domain.documents import (
    ContentHash,
    Document,
    DocumentId,
    DocumentSourceType,
    DocumentStorageState,
    DocumentVersion,
    DocumentVersionId,
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
CONTENT_HASH = "a" * 64


def test_document_upload_route_accepts_multipart_and_returns_safe_response() -> None:
    upload = FakeUploadUseCase(_upload_result())
    app = _app(upload)

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/documents",
            headers={"Authorization": "Bearer token", "Idempotency-Key": "upload-1"},
            files={"file": ("report.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 201
    assert upload.commands[0].filename == "report.pdf"
    assert upload.commands[0].declared_media_type == "application/pdf"
    body = response.json()
    assert body["outcome"] == "created"
    assert body["document"]["id"] == str(DOCUMENT_ID)
    assert body["current_version"]["storage_state"] == "stored"
    assert "storage_object_key" not in body["current_version"]


def test_document_upload_route_requires_idempotency_key() -> None:
    app = _app(FakeUploadUseCase(_upload_result()))

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/documents",
            headers={"Authorization": "Bearer token"},
            files={"file": ("report.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_document_upload_route_maps_idempotency_conflict() -> None:
    app = _app(FakeUploadUseCase(IdempotencyConflictError("key was already used")))

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/organizations/{ORG_ID}/documents",
            headers={"Authorization": "Bearer token", "Idempotency-Key": "upload-1"},
            files={"file": ("report.pdf", b"%PDF-1.7\n", "application/pdf")},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


def _app(upload: FakeUploadUseCase) -> FastAPI:
    app = create_app(Settings(environment=Environment.TEST))
    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_resolve_tenant_context] = lambda: FakeResolveTenantContext()
    app.dependency_overrides[get_independent_audit_recorder] = NullAuditRecorder
    app.dependency_overrides[get_upload_document] = lambda: upload
    return app


def _principal() -> VerifiedAccessPrincipal:
    return VerifiedAccessPrincipal(
        user_id=USER_ID,
        session_id=SessionId(SESSION_ID),
        token_id=TOKEN_ID,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _tenant() -> TenantContext:
    return TenantContext.create(
        user_id=USER_ID,
        organization_id=ORG_ID,
        membership_id=MEMBERSHIP_ID,
        role=Role.ADMIN,
    )


def _upload_result() -> UploadDocumentResult:
    version = DocumentVersion.create(
        id=DocumentVersionId(VERSION_ID),
        organization_id=ORG_ID,
        document_id=DocumentId(DOCUMENT_ID),
        version_number=1,
        original_filename="report.pdf",
        media_type="application/pdf",
        byte_size=9,
        content_hash=ContentHash(CONTENT_HASH),
        storage_state=DocumentStorageState.STORED,
        created_at=NOW,
        created_by_user_id=USER_ID,
    )
    document = Document.register(
        id=DocumentId(DOCUMENT_ID),
        organization_id=ORG_ID,
        display_filename="report.pdf",
        source_type=DocumentSourceType.UPLOAD,
        source_reference=None,
        current_version=version,
        created_by_user_id=USER_ID,
        now=NOW,
    ).mark_stored(actor_user_id=USER_ID, now=NOW)
    return UploadDocumentResult(
        document=document,
        current_version=version,
        outcome=UploadDocumentOutcome.CREATED,
        duplicate=False,
        idempotent_replay=False,
        response_status=201,
    )


class FakeUploadUseCase:
    def __init__(self, result: UploadDocumentResult | Exception) -> None:
        self._result = result
        self.commands: list[UploadDocumentCommand] = []

    async def __call__(
        self,
        command: UploadDocumentCommand,
        *,
        tenant: TenantContext,
    ) -> UploadDocumentResult:
        assert tenant.organization_id == ORG_ID
        self.commands.append(command)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeResolveTenantContext:
    async def __call__(self, command: ResolveTenantContextCommand) -> TenantContext:
        assert command.organization_id == ORG_ID
        return _tenant()


class NullAuditRecorder:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)

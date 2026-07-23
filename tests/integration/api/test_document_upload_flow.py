"""Document upload API integration flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from workflowforge_api.dependencies import get_current_principal, get_resolve_tenant_context
from workflowforge_api.factory import create_app
from workflowforge_application.authorization import ResolveTenantContextCommand, TenantContext
from workflowforge_application.identity import VerifiedAccessPrincipal
from workflowforge_domain.identity import Role, SessionId
from workflowforge_infrastructure.config import DatabaseSettings, S3Settings, Settings
from workflowforge_infrastructure.database import create_sync_migration_engine
from workflowforge_infrastructure.storage import create_s3_client

from tests.integration.database.utils import require_postgresql

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
USER_ID = UUID("10111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("10444444-4444-4444-8444-444444444444")
TOKEN_ID = UUID("10777777-7777-4777-8777-777777777777")
ORG_ID = UUID("10222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("10333333-3333-4333-8333-333333333333")


@pytest.mark.integration
def test_document_upload_persists_object_metadata_and_idempotent_outcomes() -> None:
    database_settings = require_postgresql()
    settings = Settings(database=database_settings, s3=_s3_settings())
    command.upgrade(_alembic_config(database_settings), "head")
    _seed_tenant(database_settings)
    _ensure_bucket(settings)

    app = create_app(settings)
    app.dependency_overrides[get_current_principal] = _principal
    app.dependency_overrides[get_resolve_tenant_context] = lambda: FakeResolveTenantContext()

    try:
        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/organizations/{ORG_ID}/documents",
                headers={"Authorization": "Bearer token", "Idempotency-Key": "integration-1"},
                files={"file": ("report.pdf", b"%PDF-1.7\npayload", "application/pdf")},
            )
            replay = client.post(
                f"/api/v1/organizations/{ORG_ID}/documents",
                headers={"Authorization": "Bearer token", "Idempotency-Key": "integration-1"},
                files={"file": ("report.pdf", b"%PDF-1.7\npayload", "application/pdf")},
            )
            duplicate = client.post(
                f"/api/v1/organizations/{ORG_ID}/documents",
                headers={"Authorization": "Bearer token", "Idempotency-Key": "integration-2"},
                files={"file": ("copy.pdf", b"%PDF-1.7\npayload", "application/pdf")},
            )
    finally:
        _delete_uploaded_objects(settings)

    assert first.status_code == 201
    first_body = first.json()
    assert first_body["outcome"] == "created"
    assert first_body["document"]["status"] == "stored"
    assert first_body["current_version"]["storage_state"] == "stored"
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["outcome"] == "idempotent_replay"
    assert duplicate.status_code == 200
    assert duplicate.json()["outcome"] == "duplicate"
    assert duplicate.json()["document"]["id"] == first_body["document"]["id"]


def _alembic_config(settings: DatabaseSettings) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_settings"] = settings
    return config


def _seed_tenant(settings: DatabaseSettings) -> None:
    engine = create_sync_migration_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM upload_idempotency WHERE organization_id = :organization_id"),
                {"organization_id": ORG_ID},
            )
            connection.execute(
                text("DELETE FROM security_audit_events WHERE organization_id = :organization_id"),
                {"organization_id": ORG_ID},
            )
            connection.execute(
                text("DELETE FROM documents WHERE organization_id = :organization_id"),
                {"organization_id": ORG_ID},
            )
            connection.execute(
                text(
                    "INSERT INTO users (id, email, normalized_email, display_name, is_active, "
                    "created_at, updated_at) VALUES (:user_id, 'upload@example.com', "
                    "'upload@example.com', 'Upload User', true, :now, :now) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"user_id": USER_ID, "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) "
                    "VALUES (:organization_id, 'Upload Org', 'upload-org', true, :now, :now) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"organization_id": ORG_ID, "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO memberships (id, user_id, organization_id, role, status, "
                    "invited_at, joined_at, suspended_at, removed_at, created_at, updated_at) "
                    "VALUES (:membership_id, :user_id, :organization_id, 'admin', 'active', "
                    "NULL, :now, NULL, NULL, :now, :now) ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "membership_id": MEMBERSHIP_ID,
                    "user_id": USER_ID,
                    "organization_id": ORG_ID,
                    "now": NOW,
                },
            )
    finally:
        engine.dispose()


def _ensure_bucket(settings: Settings) -> None:
    client = create_s3_client(settings.s3)
    try:
        try:
            client.create_bucket(Bucket=settings.s3.bucket)
        except Exception:
            return
    finally:
        client.close()


def _s3_settings() -> S3Settings:
    return S3Settings(
        endpoint_url="http://localhost:29000",
        access_key="workflowforge_phase3",
        secret_key=SecretStr("workflowforge_phase3_minio_secret"),
        bucket="workflowforge-phase3",
    )


def _delete_uploaded_objects(settings: Settings) -> None:
    client = create_s3_client(settings.s3)
    try:
        response = client.list_objects_v2(Bucket=settings.s3.bucket, Prefix=f"documents/{ORG_ID}/")
        objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.s3.bucket, Delete={"Objects": objects})
    finally:
        client.close()


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


class FakeResolveTenantContext:
    async def __call__(self, command: ResolveTenantContextCommand) -> TenantContext:
        assert command.organization_id == ORG_ID
        return _tenant()

"""Document application service tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from workflowforge_application.authorization import TenantContext
from workflowforge_application.documents import (
    ConcurrencyConflictError,
    DocumentArchiveCommand,
    DocumentArtifactRegistrationCommand,
    DocumentDownloadCommand,
    DocumentListFilter,
    DocumentListPage,
    DocumentNotFoundError,
    DocumentProjection,
    DocumentRegistrationCommand,
    DocumentService,
    DocumentVersionCreationCommand,
    DownloadUrl,
    DuplicateDocumentContentError,
    PromoteObjectRequest,
    PutTempObjectRequest,
    StoredObjectMetadata,
)
from workflowforge_application.identity.ports import TransactionManager
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
from workflowforge_domain.identity import Permission, Role

HASH = "b" * 64
ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_ORG = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP = UUID("99999999-9999-4999-8999-999999999999")


async def test_register_document_persists_metadata_for_tenant() -> None:
    repository = InMemoryDocumentRepository()
    transaction = SpyTransaction()
    service = DocumentService(repository, transaction=transaction)

    document = await service.register_document(_command(), tenant=_tenant(), now=_now())

    version = repository.versions[document.current_version_id]
    assert document.organization_id == ORG
    assert document.display_filename == "example.pdf"
    assert document.source_type is DocumentSourceType.UPLOAD
    assert version.content_hash == ContentHash(HASH)
    assert version.storage_object_key.value == f"documents/{ORG}/sha256/bb/bb/{HASH}"
    assert transaction.commits == 1


async def test_register_document_returns_existing_document_for_duplicate_hash_in_same_tenant() -> (
    None
):
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    first = await service.register_document(
        _command(display_filename="first.pdf"), tenant=_tenant(), now=_now()
    )

    second = await service.register_document(
        _command(display_filename="second.pdf"), tenant=_tenant(), now=_now()
    )

    assert second == first
    assert len(repository.documents) == 1


async def test_same_hash_in_different_tenants_can_register_different_documents() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)

    first = await service.register_document(
        _command(), tenant=_tenant(organization_id=ORG), now=_now()
    )
    second = await service.register_document(
        _command(), tenant=_tenant(organization_id=OTHER_ORG), now=_now()
    )

    assert second.id != first.id
    assert second.organization_id == OTHER_ORG


async def test_register_document_rolls_back_unresolvable_duplicate() -> None:
    repository = InMemoryDocumentRepository(raise_duplicate_on_add=True)
    transaction = SpyTransaction()
    service = DocumentService(repository, transaction=transaction)

    with pytest.raises(DuplicateDocumentContentError):
        await service.register_document(_command(), tenant=_tenant(), now=_now())

    assert transaction.rollbacks == 1


async def test_get_document_requires_tenant_scope() -> None:
    repository = InMemoryDocumentRepository()
    document = await DocumentService(repository).register_document(
        _command(), tenant=_tenant(), now=_now()
    )

    found = await DocumentService(repository).get_document(document.id, tenant=_tenant())

    assert found == document
    with pytest.raises(DocumentNotFoundError):
        await DocumentService(repository).get_document(
            document.id, tenant=_tenant(organization_id=OTHER_ORG)
        )


async def test_list_documents_uses_tenant_filter() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    await service.register_document(
        _command(display_filename="first.pdf"), tenant=_tenant(), now=_now()
    )
    await service.register_document(
        _command(display_filename="other.pdf"),
        tenant=_tenant(organization_id=OTHER_ORG),
        now=_now(),
    )

    page = await service.list_documents(tenant=_tenant(), query=DocumentListFilter(limit=10))
    projections = page.items

    assert [projection.organization_id for projection in projections] == [ORG]


async def test_archive_document_requires_permission_and_persists_state() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    document = await service.register_document(_command(), tenant=_tenant(), now=_now())

    archived = await service.archive_document(document.id, tenant=_tenant(), now=_now(6))

    assert archived.archived_by_user_id == USER
    assert repository.documents[(ORG, document.id)] == archived
    with pytest.raises(Exception, match="Permission denied"):
        await service.archive_document(
            document.id, tenant=_tenant(permissions=[Permission.DOCUMENT_READ]), now=_now(7)
        )


async def test_document_versions_artifacts_and_download_urls() -> None:
    repository = InMemoryDocumentRepository()
    audit = SpyAudit()
    service = DocumentService(repository, audit=audit)
    document = await service.register_document(_command(), tenant=_tenant(), now=_now())
    version = await service.create_version(
        DocumentVersionCreationCommand(
            document_id=document.id,
            original_filename='second "draft"\r\n.pdf',
            media_type="application/pdf",
            byte_size=456,
            content_hash="c" * 64,
            storage_state=DocumentStorageState.STORED,
        ),
        tenant=_tenant(),
        now=_now(6),
    )
    artifact = await service.register_artifact(
        DocumentArtifactRegistrationCommand(
            document_id=document.id,
            document_version_id=version.id,
            artifact_type=DocumentArtifactType.TEXT,
            media_type="text/plain",
            byte_size=12,
            content_hash="d" * 64,
            storage_object_key=StorageObjectKey(
                f"artifacts/{ORG}/{document.id.value}/{version.id.value}/text/demo.txt"
            ),
            metadata={"lang": "en"},
        ),
        tenant=_tenant(),
        now=_now(7),
    )

    versions = await service.list_versions(document.id, tenant=_tenant())
    artifacts = await service.list_artifacts(document.id, tenant=_tenant())
    current_download = await service.create_download_url(
        DocumentDownloadCommand(document_id=document.id),
        tenant=_tenant(permissions=_download_permissions()),
        storage=SpyStorage(),
        now=_now(8),
    )
    version_download = await service.create_download_url(
        DocumentDownloadCommand(document_id=document.id, version_id=version.id),
        tenant=_tenant(permissions=_download_permissions()),
        storage=SpyStorage(),
        now=_now(9),
    )
    artifact_download = await service.create_download_url(
        DocumentDownloadCommand(document_id=document.id, artifact_id=artifact.id),
        tenant=_tenant(permissions=_artifact_download_permissions()),
        storage=SpyStorage(),
        now=_now(10),
    )

    assert versions[-1] == version
    assert artifacts == [artifact]
    assert current_download.filename == "second 'draft'.pdf"
    assert version_download.byte_size == 456
    assert artifact_download.media_type == "text/plain"
    assert len(audit.events) == 6


async def test_archive_document_with_lock_detects_concurrent_change() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    document = await service.register_document(_command(), tenant=_tenant(), now=_now())

    with pytest.raises(ConcurrencyConflictError):
        await service.archive_document_with_lock(
            DocumentArchiveCommand(document_id=document.id, expected_lock_version=99),
            tenant=_tenant(),
            now=_now(6),
        )


async def test_document_artifact_and_version_not_found_paths() -> None:
    repository = InMemoryDocumentRepository()
    service = DocumentService(repository)
    document = await service.register_document(_command(), tenant=_tenant(), now=_now())

    with pytest.raises(DocumentNotFoundError):
        await service.get_version(
            tenant=_tenant(),
            document_id=document.id,
            version_id=DocumentVersionId(UUID("44444444-4444-4444-8444-444444444444")),
        )
    with pytest.raises(DocumentNotFoundError):
        await service.get_artifact(
            tenant=_tenant(),
            document_id=document.id,
            artifact_id=DocumentArtifactId(UUID("55555555-5555-4555-8555-555555555555")),
        )


async def test_application_service_has_no_infrastructure_dependency() -> None:
    import workflowforge_application.documents.service as service_module

    assert "workflowforge_infrastructure" not in service_module.__dict__


class InMemoryDocumentRepository:
    def __init__(self, *, raise_duplicate_on_add: bool = False) -> None:
        self.documents: dict[tuple[UUID, DocumentId], Document] = {}
        self.versions: dict[DocumentVersionId, DocumentVersion] = {}
        self.by_hash: dict[tuple[UUID, ContentHash], Document] = {}
        self.artifacts: dict[DocumentArtifactId, DocumentArtifact] = {}
        self.raise_duplicate_on_add = raise_duplicate_on_add

    async def add_document(self, document: Document, version: DocumentVersion) -> Document:
        if (
            self.raise_duplicate_on_add
            or (document.organization_id, version.content_hash) in self.by_hash
        ):
            msg = "duplicate"
            raise DuplicateDocumentContentError(msg)
        self.documents[(document.organization_id, document.id)] = document
        self.versions[version.id] = version
        self.by_hash[(document.organization_id, version.content_hash)] = document
        return document

    async def get_document(
        self, *, organization_id: UUID, document_id: DocumentId
    ) -> Document | None:
        return self.documents.get((organization_id, document_id))

    async def get_document_for_update(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> Document | None:
        return await self.get_document(organization_id=organization_id, document_id=document_id)

    async def find_document_by_tenant_content_hash(
        self,
        *,
        organization_id: UUID,
        content_hash: ContentHash,
    ) -> Document | None:
        return self.by_hash.get((organization_id, content_hash))

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        query: DocumentListFilter,
    ) -> DocumentListPage:
        items = [
            DocumentProjection(
                id=document.id,
                organization_id=document.organization_id,
                display_filename=document.display_filename,
                source_type=document.source_type,
                status=document.status,
                current_version_id=document.current_version_id,
                media_type=self.versions[document.current_version_id].media_type,
                byte_size=self.versions[document.current_version_id].byte_size,
                storage_state=self.versions[document.current_version_id].storage_state.value,
                created_at=document.created_at,
                updated_at=document.updated_at,
                lock_version=document.lock_version,
            )
            for (tenant_id, _), document in self.documents.items()
            if tenant_id == organization_id
        ][: query.limit]
        return DocumentListPage(
            items=items,
            total=len(items),
            limit=query.limit,
            offset=query.offset,
        )

    async def archive_document(self, document: Document) -> Document:
        self.documents[(document.organization_id, document.id)] = document
        return document

    async def add_version(self, version: DocumentVersion) -> DocumentVersion:
        self.versions[version.id] = version
        return version

    async def get_version(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion | None:
        version = self.versions.get(version_id)
        if (
            version is None
            or version.organization_id != organization_id
            or version.document_id != document_id
        ):
            return None
        return version

    async def list_versions(
        self, *, organization_id: UUID, document_id: DocumentId
    ) -> list[DocumentVersion]:
        return [
            version
            for version in self.versions.values()
            if version.organization_id == organization_id and version.document_id == document_id
        ]

    async def set_current_version(
        self, *, document: Document, version: DocumentVersion
    ) -> Document:
        self.documents[(document.organization_id, document.id)] = document
        return document

    async def add_artifact(self, artifact: DocumentArtifact) -> DocumentArtifact:
        self.artifacts[artifact.id] = artifact
        return artifact

    async def get_artifact(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        artifact_id: DocumentArtifactId,
    ) -> DocumentArtifact | None:
        artifact = self.artifacts.get(artifact_id)
        if (
            artifact is None
            or artifact.organization_id != organization_id
            or artifact.document_id != document_id
        ):
            return None
        return artifact

    async def list_artifacts(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
    ) -> list[DocumentArtifact]:
        return [
            artifact
            for artifact in self.artifacts.values()
            if artifact.organization_id == organization_id and artifact.document_id == document_id
        ]

    async def mark_version_stored(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        return await self._mark_version_storage_state(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
            storage_state=DocumentStorageState.STORED,
        )

    async def mark_version_failed(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
    ) -> DocumentVersion:
        return await self._mark_version_storage_state(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
            storage_state=DocumentStorageState.FAILED,
        )

    async def _mark_version_storage_state(
        self,
        *,
        organization_id: UUID,
        document_id: DocumentId,
        version_id: DocumentVersionId,
        storage_state: DocumentStorageState,
    ) -> DocumentVersion:
        version = await self.get_version(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
        )
        if version is None:
            msg = "version not found"
            raise ValueError(msg)
        updated = DocumentVersion(
            id=version.id,
            organization_id=version.organization_id,
            document_id=version.document_id,
            version_number=version.version_number,
            original_filename=version.original_filename,
            media_type=version.media_type,
            byte_size=version.byte_size,
            content_hash=version.content_hash,
            storage_object_key=version.storage_object_key,
            storage_state=storage_state,
            created_at=version.created_at,
            created_by_user_id=version.created_by_user_id,
        )
        self.versions[version_id] = updated
        return updated


class SpyTransaction(TransactionManager):
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class SpyAudit:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def record(self, event: object) -> None:
        self.events.append(event)


class SpyStorage:
    async def put_temp_stream(self, request: PutTempObjectRequest) -> StoredObjectMetadata:
        return StoredObjectMetadata(key=request.key, byte_size=0, media_type=request.media_type)

    async def promote_temp_object(self, request: PromoteObjectRequest) -> StoredObjectMetadata:
        return StoredObjectMetadata(key=request.destination_key, byte_size=0)

    async def head_object(self, key: StorageObjectKey) -> StoredObjectMetadata | None:
        return StoredObjectMetadata(key=key, byte_size=0)

    async def delete_object(self, key: StorageObjectKey) -> None:
        _ = key

    async def create_download_url(
        self,
        *,
        key: StorageObjectKey,
        expires_in_seconds: int,
        now: datetime,
    ) -> DownloadUrl:
        return DownloadUrl(
            url=f"https://storage.example/{key.value}?ttl={expires_in_seconds}",
            expires_at=now,
        )


def _command(*, display_filename: str = "example.pdf") -> DocumentRegistrationCommand:
    return DocumentRegistrationCommand(
        display_filename=display_filename,
        media_type="application/pdf",
        byte_size=123,
        content_hash=HASH,
    )


def _tenant(
    *,
    organization_id: UUID = ORG,
    permissions: list[Permission] | None = None,
) -> TenantContext:
    return TenantContext.trusted_with_permissions(
        user_id=USER,
        organization_id=organization_id,
        membership_id=MEMBERSHIP,
        role=Role.OPERATOR,
        permissions=permissions
        or [
            Permission.DOCUMENT_READ,
            Permission.DOCUMENT_WRITE,
            Permission.DOCUMENT_ARCHIVE,
            Permission.DOCUMENT_VERSION_READ,
            Permission.DOCUMENT_VERSION_CREATE,
            Permission.ARTIFACT_READ,
        ],
    )


def _download_permissions() -> list[Permission]:
    return [
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_DOWNLOAD,
        Permission.DOCUMENT_VERSION_READ,
    ]


def _artifact_download_permissions() -> list[Permission]:
    return [
        Permission.DOCUMENT_READ,
        Permission.ARTIFACT_READ,
        Permission.ARTIFACT_DOWNLOAD,
    ]


def _now(second: int = 5) -> datetime:
    return datetime(2026, 1, 2, 3, 4, second, tzinfo=UTC)

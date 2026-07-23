"""Case API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CaseResponse(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    summary: str | None
    status: str
    priority: str
    external_reference: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    archived_at: datetime | None
    lock_version: int


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int
    limit: int
    offset: int


class CreateCaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=4000)
    priority: str = "normal"
    external_reference: str | None = Field(default=None, max_length=255)


class UpdateCaseRequest(BaseModel):
    lock_version: int
    title: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=4000)
    priority: str | None = None
    external_reference: str | None = Field(default=None, max_length=255)


class CaseStateRequest(BaseModel):
    lock_version: int


class CaseDocumentRequest(BaseModel):
    document_id: UUID


class CaseDocumentResponse(BaseModel):
    id: UUID
    case_id: UUID
    document_id: UUID
    added_at: datetime
    added_by_user_id: UUID


class CreateCaseCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CaseCommentResponse(BaseModel):
    id: UUID
    case_id: UUID
    body: str
    created_at: datetime
    created_by_user_id: UUID


class CreateCaseTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None


class UpdateCaseTaskRequest(BaseModel):
    lock_version: int
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None


class CaseTaskResponse(BaseModel):
    id: UUID
    case_id: UUID
    title: str
    description: str | None
    status: str
    assigned_to_user_id: UUID | None
    due_at: datetime | None
    completed_at: datetime | None
    lock_version: int


class CreateCaseDecisionRequest(BaseModel):
    decision_type: str = Field(min_length=1, max_length=255)
    rationale: str = Field(min_length=1, max_length=4000)


class CaseDecisionResponse(BaseModel):
    id: UUID
    case_id: UUID
    decision_type: str
    rationale: str
    created_at: datetime
    created_by_user_id: UUID


class CaseDetailResponse(BaseModel):
    case: CaseResponse
    documents: list[CaseDocumentResponse]
    comments: list[CaseCommentResponse]
    tasks: list[CaseTaskResponse]
    decisions: list[CaseDecisionResponse]

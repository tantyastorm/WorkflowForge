import { apiClient } from "../../lib/api-client";
import type {
  Batch,
  BatchDocument,
  BatchDocumentsResponse,
  BatchListResponse,
  CaseDetailResponse,
  CaseListResponse,
  CaseRecord,
  DocumentDetailResponse,
  DocumentListResponse,
  DownloadUrlResponse,
  UploadDocumentResponse,
} from "./types";

const API_PREFIX = "/api/v1/organizations";

export async function listDocuments(organizationId: string) {
  return (
    await apiClient.request<DocumentListResponse>(
      `${API_PREFIX}/${organizationId}/documents?limit=50&archived=false`,
      { authenticated: true },
    )
  ).data;
}

export async function getDocument(organizationId: string, documentId: string) {
  return (
    await apiClient.request<DocumentDetailResponse>(
      `${API_PREFIX}/${organizationId}/documents/${documentId}`,
      { authenticated: true },
    )
  ).data;
}

export async function uploadDocument(organizationId: string, file: File) {
  const formData = new FormData();
  formData.set("file", file);
  return (
    await apiClient.request<UploadDocumentResponse>(`${API_PREFIX}/${organizationId}/documents`, {
      method: "POST",
      rawBody: formData,
      headers: { "Idempotency-Key": crypto.randomUUID() },
      authenticated: true,
      timeoutMs: 60_000,
    })
  ).data;
}

export async function archiveDocument(
  organizationId: string,
  documentId: string,
  lockVersion: number,
) {
  return (
    await apiClient.request<DocumentDetailResponse["document"]>(
      `${API_PREFIX}/${organizationId}/documents/${documentId}/archive`,
      { method: "POST", body: { lock_version: lockVersion }, authenticated: true },
    )
  ).data;
}

export async function createDocumentDownload(organizationId: string, documentId: string) {
  return (
    await apiClient.request<DownloadUrlResponse>(
      `${API_PREFIX}/${organizationId}/documents/${documentId}/download`,
      { authenticated: true },
    )
  ).data;
}

export async function listBatches(organizationId: string) {
  return (
    await apiClient.request<BatchListResponse>(
      `${API_PREFIX}/${organizationId}/batches?limit=50&archived=false`,
      { authenticated: true },
    )
  ).data;
}

export async function createBatch(
  organizationId: string,
  input: { name: string; description?: string; external_reference?: string },
) {
  return (
    await apiClient.request<Batch>(`${API_PREFIX}/${organizationId}/batches`, {
      method: "POST",
      body: input,
      authenticated: true,
    })
  ).data;
}

export async function addBatchDocument(
  organizationId: string,
  batchId: string,
  documentId: string,
) {
  return (
    await apiClient.request<BatchDocument>(
      `${API_PREFIX}/${organizationId}/batches/${batchId}/documents`,
      { method: "POST", body: { document_id: documentId }, authenticated: true },
    )
  ).data;
}

export async function listBatchDocuments(organizationId: string, batchId: string) {
  return (
    await apiClient.request<BatchDocumentsResponse>(
      `${API_PREFIX}/${organizationId}/batches/${batchId}/documents`,
      { authenticated: true },
    )
  ).data;
}

export async function archiveBatch(organizationId: string, batchId: string, lockVersion: number) {
  return (
    await apiClient.request<Batch>(`${API_PREFIX}/${organizationId}/batches/${batchId}/archive`, {
      method: "POST",
      body: { lock_version: lockVersion },
      authenticated: true,
    })
  ).data;
}

export async function listCases(organizationId: string) {
  return (
    await apiClient.request<CaseListResponse>(
      `${API_PREFIX}/${organizationId}/cases?limit=50&archived=false`,
      { authenticated: true },
    )
  ).data;
}

export async function getCase(organizationId: string, caseId: string) {
  return (
    await apiClient.request<CaseDetailResponse>(`${API_PREFIX}/${organizationId}/cases/${caseId}`, {
      authenticated: true,
    })
  ).data;
}

export async function createCase(
  organizationId: string,
  input: { title: string; summary?: string; priority: string; external_reference?: string },
) {
  return (
    await apiClient.request<CaseRecord>(`${API_PREFIX}/${organizationId}/cases`, {
      method: "POST",
      body: input,
      authenticated: true,
    })
  ).data;
}

export async function addCaseDocument(organizationId: string, caseId: string, documentId: string) {
  return (
    await apiClient.request(`${API_PREFIX}/${organizationId}/cases/${caseId}/documents`, {
      method: "POST",
      body: { document_id: documentId },
      authenticated: true,
    })
  ).data;
}

export async function addCaseComment(organizationId: string, caseId: string, body: string) {
  return (
    await apiClient.request(`${API_PREFIX}/${organizationId}/cases/${caseId}/comments`, {
      method: "POST",
      body: { body },
      authenticated: true,
    })
  ).data;
}

export async function addCaseTask(organizationId: string, caseId: string, title: string) {
  return (
    await apiClient.request(`${API_PREFIX}/${organizationId}/cases/${caseId}/tasks`, {
      method: "POST",
      body: { title },
      authenticated: true,
    })
  ).data;
}

export async function addCaseDecision(
  organizationId: string,
  caseId: string,
  input: { decision_type: string; rationale: string },
) {
  return (
    await apiClient.request(`${API_PREFIX}/${organizationId}/cases/${caseId}/decisions`, {
      method: "POST",
      body: input,
      authenticated: true,
    })
  ).data;
}

export async function changeCaseState(
  organizationId: string,
  caseId: string,
  action: "close" | "reopen" | "archive",
  lockVersion: number,
) {
  return (
    await apiClient.request<CaseRecord>(
      `${API_PREFIX}/${organizationId}/cases/${caseId}/${action}`,
      { method: "POST", body: { lock_version: lockVersion }, authenticated: true },
    )
  ).data;
}

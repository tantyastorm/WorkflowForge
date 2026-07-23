export type DocumentSummary = {
  id: string;
  organization_id: string;
  display_filename: string;
  source_type: string;
  status: string;
  current_version_id: string;
  media_type: string;
  byte_size: number;
  storage_state: string;
  created_at: string;
  updated_at: string;
  lock_version: number;
};

export type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type DocumentDetailResponse = {
  document: DocumentSummary;
  current_version: {
    id: string;
    version_number: number;
    original_filename: string;
    media_type: string;
    byte_size: number;
    storage_state: string;
    created_at: string;
  };
};

export type DownloadUrlResponse = {
  url: string;
  filename: string;
  media_type: string;
  byte_size: number;
  expires_at: string;
};

export type UploadDocumentResponse = {
  document: DocumentSummary;
  outcome: string;
  duplicate: boolean;
  idempotent_replay: boolean;
};

export type Batch = {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: string;
  external_reference: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  lock_version: number;
};

export type BatchListResponse = {
  items: Batch[];
  total: number;
  limit: number;
  offset: number;
};

export type BatchDocument = {
  id: string;
  batch_id: string;
  document_id: string;
  added_at: string;
  added_by_user_id: string;
};

export type BatchDocumentsResponse = {
  items: BatchDocument[];
};

export type CaseRecord = {
  id: string;
  organization_id: string;
  title: string;
  summary: string | null;
  status: string;
  priority: string;
  external_reference: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  archived_at: string | null;
  lock_version: number;
};

export type CaseListResponse = {
  items: CaseRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type CaseDetailResponse = {
  case: CaseRecord;
  documents: Array<{ id: string; case_id: string; document_id: string; added_at: string }>;
  comments: Array<{ id: string; body: string; created_at: string; created_by_user_id: string }>;
  tasks: Array<{
    id: string;
    title: string;
    description: string | null;
    status: string;
    due_at: string | null;
    completed_at: string | null;
    lock_version: number;
  }>;
  decisions: Array<{ id: string; decision_type: string; rationale: string; created_at: string }>;
};

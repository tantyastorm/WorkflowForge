import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState } from "../../components/feedback/ErrorState";
import { LoadingState } from "../../components/feedback/LoadingState";
import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "../auth/auth-context";
import {
  archiveDocument,
  createDocumentDownload,
  getDocument,
  listDocuments,
  uploadDocument,
} from "./api";
import { errorMessage, formatBytes, formatDate } from "./format";

export function DocumentsPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const organizationId = auth.selectedOrganizationId ?? "";
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents", organizationId],
    queryFn: () => listDocuments(organizationId),
    enabled: organizationId !== "",
  });
  const selectedDocument = documentsQuery.data?.items.find(
    (document) => document.id === selectedDocumentId,
  );
  const detailQuery = useQuery({
    queryKey: ["documents", organizationId, selectedDocumentId],
    queryFn: () => getDocument(organizationId, selectedDocumentId ?? ""),
    enabled: organizationId !== "" && selectedDocumentId !== null,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDocument(organizationId, file),
    onSuccess: async (result) => {
      setSelectedDocumentId(result.document.id);
      await queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
    },
  });
  const archiveMutation = useMutation({
    mutationFn: () =>
      archiveDocument(
        organizationId,
        selectedDocument?.id ?? "",
        selectedDocument?.lock_version ?? 0,
      ),
    onSuccess: async () => {
      setSelectedDocumentId(null);
      await queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
    },
  });
  const downloadMutation = useMutation({
    mutationFn: (documentId: string) => createDocumentDownload(organizationId, documentId),
    onSuccess: (download) => {
      window.open(download.url, "_blank", "noopener,noreferrer");
    },
  });

  if (documentsQuery.isPending) {
    return (
      <PageContainer>
        <LoadingState message="Loading documents" />
      </PageContainer>
    );
  }

  if (documentsQuery.isError) {
    return (
      <PageContainer>
        <ErrorState title="Documents unavailable" message={errorMessage(documentsQuery.error)} />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="work-page">
        <header className="work-page__header">
          <div>
            <p className="work-page__eyebrow">Intake</p>
            <h1>Documents</h1>
          </div>
          <label className="button work-upload">
            Upload
            <input
              type="file"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (file !== undefined) {
                  uploadMutation.mutate(file);
                }
              }}
            />
          </label>
        </header>
        <StatusLine
          error={uploadMutation.error ?? archiveMutation.error ?? downloadMutation.error}
          pending={
            uploadMutation.isPending || archiveMutation.isPending || downloadMutation.isPending
          }
        />
        <div className="work-layout">
          <section aria-labelledby="document-list-heading">
            <h2 id="document-list-heading">Active documents</h2>
            <div className="work-table" role="table" aria-label="Documents">
              {documentsQuery.data.items.map((document) => (
                <button
                  key={document.id}
                  className="work-row"
                  type="button"
                  onClick={() => {
                    setSelectedDocumentId(document.id);
                  }}
                >
                  <span>
                    <strong>{document.display_filename}</strong>
                    <small>{document.media_type}</small>
                  </span>
                  <span>{formatBytes(document.byte_size)}</span>
                  <span>{document.storage_state}</span>
                  <span>{formatDate(document.updated_at)}</span>
                </button>
              ))}
              {documentsQuery.data.items.length === 0 ? (
                <p className="work-empty">No active documents.</p>
              ) : null}
            </div>
          </section>
          <aside className="work-detail" aria-label="Document details">
            {selectedDocument === undefined ? (
              <p className="work-empty">Select a document.</p>
            ) : (
              <>
                <h2>{selectedDocument.display_filename}</h2>
                <dl className="work-meta">
                  <dt>Status</dt>
                  <dd>{selectedDocument.status}</dd>
                  <dt>Version</dt>
                  <dd>{detailQuery.data?.current_version.version_number ?? "Loading"}</dd>
                  <dt>Created</dt>
                  <dd>{formatDate(selectedDocument.created_at)}</dd>
                  <dt>ID</dt>
                  <dd>{selectedDocument.id}</dd>
                </dl>
                <div className="work-actions">
                  <button
                    className="button"
                    type="button"
                    onClick={() => {
                      downloadMutation.mutate(selectedDocument.id);
                    }}
                  >
                    Download
                  </button>
                  <button
                    className="button button--danger"
                    type="button"
                    onClick={() => {
                      archiveMutation.mutate();
                    }}
                  >
                    Archive
                  </button>
                </div>
              </>
            )}
          </aside>
        </div>
      </div>
    </PageContainer>
  );
}

function StatusLine({ error, pending }: { error: unknown; pending: boolean }) {
  if (pending) {
    return <p className="work-status">Working...</p>;
  }
  if (error !== null) {
    return (
      <p className="work-status work-status--error" role="status">
        {errorMessage(error)}
      </p>
    );
  }
  return null;
}

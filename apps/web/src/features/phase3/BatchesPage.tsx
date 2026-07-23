import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState } from "../../components/feedback/ErrorState";
import { LoadingState } from "../../components/feedback/LoadingState";
import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "../auth/auth-context";
import {
  addBatchDocument,
  archiveBatch,
  createBatch,
  listBatchDocuments,
  listBatches,
  listDocuments,
} from "./api";
import { errorMessage, formatDate } from "./format";

export function BatchesPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const organizationId = auth.selectedOrganizationId ?? "";
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [documentId, setDocumentId] = useState("");

  const batchesQuery = useQuery({
    queryKey: ["batches", organizationId],
    queryFn: () => listBatches(organizationId),
    enabled: organizationId !== "",
  });
  const documentsQuery = useQuery({
    queryKey: ["documents", organizationId],
    queryFn: () => listDocuments(organizationId),
    enabled: organizationId !== "",
  });
  const selectedBatch = batchesQuery.data?.items.find((batch) => batch.id === selectedBatchId);
  const membershipsQuery = useQuery({
    queryKey: ["batches", organizationId, selectedBatchId, "documents"],
    queryFn: () => listBatchDocuments(organizationId, selectedBatchId ?? ""),
    enabled: organizationId !== "" && selectedBatchId !== null,
  });

  const createMutation = useMutation({
    mutationFn: () => createBatch(organizationId, { name }),
    onSuccess: async (batch) => {
      setName("");
      setSelectedBatchId(batch.id);
      await queryClient.invalidateQueries({ queryKey: ["batches", organizationId] });
    },
  });
  const addDocumentMutation = useMutation({
    mutationFn: () => addBatchDocument(organizationId, selectedBatchId ?? "", documentId),
    onSuccess: async () => {
      setDocumentId("");
      await queryClient.invalidateQueries({ queryKey: ["batches", organizationId] });
    },
  });
  const archiveMutation = useMutation({
    mutationFn: () =>
      archiveBatch(organizationId, selectedBatch?.id ?? "", selectedBatch?.lock_version ?? 0),
    onSuccess: async () => {
      setSelectedBatchId(null);
      await queryClient.invalidateQueries({ queryKey: ["batches", organizationId] });
    },
  });

  if (batchesQuery.isPending) {
    return (
      <PageContainer>
        <LoadingState message="Loading batches" />
      </PageContainer>
    );
  }

  if (batchesQuery.isError) {
    return (
      <PageContainer>
        <ErrorState title="Batches unavailable" message={errorMessage(batchesQuery.error)} />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="work-page">
        <header className="work-page__header">
          <div>
            <p className="work-page__eyebrow">Grouping</p>
            <h1>Batches</h1>
          </div>
          <form
            className="work-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (name.trim() !== "") {
                createMutation.mutate();
              }
            }}
          >
            <input
              aria-label="Batch name"
              placeholder="Batch name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
            <button className="button" type="submit" disabled={createMutation.isPending}>
              Create
            </button>
          </form>
        </header>
        <StatusLine
          error={createMutation.error ?? addDocumentMutation.error ?? archiveMutation.error}
          pending={
            createMutation.isPending || addDocumentMutation.isPending || archiveMutation.isPending
          }
        />
        <div className="work-layout">
          <section aria-labelledby="batch-list-heading">
            <h2 id="batch-list-heading">Active batches</h2>
            <div className="work-table">
              {batchesQuery.data.items.map((batch) => (
                <button
                  key={batch.id}
                  className="work-row"
                  type="button"
                  onClick={() => {
                    setSelectedBatchId(batch.id);
                  }}
                >
                  <span>
                    <strong>{batch.name}</strong>
                    <small>{batch.external_reference ?? batch.id}</small>
                  </span>
                  <span>{batch.status}</span>
                  <span>{formatDate(batch.updated_at)}</span>
                </button>
              ))}
              {batchesQuery.data.items.length === 0 ? (
                <p className="work-empty">No active batches.</p>
              ) : null}
            </div>
          </section>
          <aside className="work-detail" aria-label="Batch details">
            {selectedBatch === undefined ? (
              <p className="work-empty">Select a batch.</p>
            ) : (
              <>
                <h2>{selectedBatch.name}</h2>
                <dl className="work-meta">
                  <dt>Status</dt>
                  <dd>{selectedBatch.status}</dd>
                  <dt>Documents</dt>
                  <dd>{String(membershipsQuery.data?.items.length ?? 0)}</dd>
                  <dt>Updated</dt>
                  <dd>{formatDate(selectedBatch.updated_at)}</dd>
                </dl>
                <form
                  className="work-stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (documentId !== "") {
                      addDocumentMutation.mutate();
                    }
                  }}
                >
                  <select
                    aria-label="Document"
                    value={documentId}
                    onChange={(event) => {
                      setDocumentId(event.target.value);
                    }}
                  >
                    <option value="">Choose a document</option>
                    {documentsQuery.data?.items.map((document) => (
                      <option key={document.id} value={document.id}>
                        {document.display_filename}
                      </option>
                    ))}
                  </select>
                  <button className="button" type="submit">
                    Add document
                  </button>
                </form>
                <div className="work-chip-list">
                  {membershipsQuery.data?.items.map((membership) => (
                    <span key={membership.id}>{membership.document_id}</span>
                  ))}
                </div>
                <button
                  className="button button--danger"
                  type="button"
                  onClick={() => {
                    archiveMutation.mutate();
                  }}
                >
                  Archive batch
                </button>
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

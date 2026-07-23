import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorState } from "../../components/feedback/ErrorState";
import { LoadingState } from "../../components/feedback/LoadingState";
import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "../auth/auth-context";
import {
  addCaseComment,
  addCaseDecision,
  addCaseDocument,
  addCaseTask,
  changeCaseState,
  createCase,
  getCase,
  listCases,
  listDocuments,
} from "./api";
import { errorMessage, formatDate } from "./format";

export function CasesPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const organizationId = auth.selectedOrganizationId ?? "";
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("normal");
  const [documentId, setDocumentId] = useState("");
  const [comment, setComment] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [decisionType, setDecisionType] = useState("");
  const [rationale, setRationale] = useState("");

  const casesQuery = useQuery({
    queryKey: ["cases", organizationId],
    queryFn: () => listCases(organizationId),
    enabled: organizationId !== "",
  });
  const documentsQuery = useQuery({
    queryKey: ["documents", organizationId],
    queryFn: () => listDocuments(organizationId),
    enabled: organizationId !== "",
  });
  const detailQuery = useQuery({
    queryKey: ["cases", organizationId, selectedCaseId],
    queryFn: () => getCase(organizationId, selectedCaseId ?? ""),
    enabled: organizationId !== "" && selectedCaseId !== null,
  });
  const selectedCase =
    detailQuery.data?.case ?? casesQuery.data?.items.find((item) => item.id === selectedCaseId);

  const invalidateCase = async () => {
    await queryClient.invalidateQueries({ queryKey: ["cases", organizationId] });
  };
  const createMutation = useMutation({
    mutationFn: () => createCase(organizationId, { title, priority }),
    onSuccess: async (record) => {
      setTitle("");
      setSelectedCaseId(record.id);
      await invalidateCase();
    },
  });
  const documentMutation = useMutation({
    mutationFn: () => addCaseDocument(organizationId, selectedCaseId ?? "", documentId),
    onSuccess: async () => {
      setDocumentId("");
      await invalidateCase();
    },
  });
  const commentMutation = useMutation({
    mutationFn: () => addCaseComment(organizationId, selectedCaseId ?? "", comment),
    onSuccess: async () => {
      setComment("");
      await invalidateCase();
    },
  });
  const taskMutation = useMutation({
    mutationFn: () => addCaseTask(organizationId, selectedCaseId ?? "", taskTitle),
    onSuccess: async () => {
      setTaskTitle("");
      await invalidateCase();
    },
  });
  const decisionMutation = useMutation({
    mutationFn: () =>
      addCaseDecision(organizationId, selectedCaseId ?? "", {
        decision_type: decisionType,
        rationale,
      }),
    onSuccess: async () => {
      setDecisionType("");
      setRationale("");
      await invalidateCase();
    },
  });
  const stateMutation = useMutation({
    mutationFn: (action: "close" | "reopen" | "archive") =>
      changeCaseState(
        organizationId,
        selectedCase?.id ?? "",
        action,
        selectedCase?.lock_version ?? 0,
      ),
    onSuccess: async (record) => {
      setSelectedCaseId(record.status === "archived" ? null : record.id);
      await invalidateCase();
    },
  });

  if (casesQuery.isPending) {
    return (
      <PageContainer>
        <LoadingState message="Loading cases" />
      </PageContainer>
    );
  }

  if (casesQuery.isError) {
    return (
      <PageContainer>
        <ErrorState title="Cases unavailable" message={errorMessage(casesQuery.error)} />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="work-page">
        <header className="work-page__header">
          <div>
            <p className="work-page__eyebrow">Casework</p>
            <h1>Cases</h1>
          </div>
          <form
            className="work-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (title.trim() !== "") {
                createMutation.mutate();
              }
            }}
          >
            <input
              aria-label="Case title"
              placeholder="Case title"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
            />
            <select
              aria-label="Priority"
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value);
              }}
            >
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
              <option value="urgent">Urgent</option>
            </select>
            <button className="button" type="submit">
              Create
            </button>
          </form>
        </header>
        <StatusLine
          error={
            createMutation.error ??
            documentMutation.error ??
            commentMutation.error ??
            taskMutation.error ??
            decisionMutation.error ??
            stateMutation.error
          }
          pending={[
            createMutation,
            documentMutation,
            commentMutation,
            taskMutation,
            decisionMutation,
            stateMutation,
          ].some((mutation) => mutation.isPending)}
        />
        <div className="work-layout">
          <section aria-labelledby="case-list-heading">
            <h2 id="case-list-heading">Active cases</h2>
            <div className="work-table">
              {casesQuery.data.items.map((record) => (
                <button
                  key={record.id}
                  className="work-row"
                  type="button"
                  onClick={() => {
                    setSelectedCaseId(record.id);
                  }}
                >
                  <span>
                    <strong>{record.title}</strong>
                    <small>{record.id}</small>
                  </span>
                  <span>{record.priority}</span>
                  <span>{record.status}</span>
                  <span>{formatDate(record.updated_at)}</span>
                </button>
              ))}
              {casesQuery.data.items.length === 0 ? (
                <p className="work-empty">No active cases.</p>
              ) : null}
            </div>
          </section>
          <aside className="work-detail work-detail--wide" aria-label="Case details">
            {selectedCase === undefined ? (
              <p className="work-empty">Select a case.</p>
            ) : (
              <>
                <h2>{selectedCase.title}</h2>
                <dl className="work-meta">
                  <dt>Status</dt>
                  <dd>{selectedCase.status}</dd>
                  <dt>Priority</dt>
                  <dd>{selectedCase.priority}</dd>
                  <dt>Updated</dt>
                  <dd>{formatDate(selectedCase.updated_at)}</dd>
                </dl>
                <div className="work-actions">
                  <button
                    className="button"
                    type="button"
                    onClick={() => {
                      stateMutation.mutate(selectedCase.status === "closed" ? "reopen" : "close");
                    }}
                  >
                    {selectedCase.status === "closed" ? "Reopen" : "Close"}
                  </button>
                  <button
                    className="button button--danger"
                    type="button"
                    onClick={() => {
                      stateMutation.mutate("archive");
                    }}
                  >
                    Archive
                  </button>
                </div>
                <form
                  className="work-stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (documentId !== "") {
                      documentMutation.mutate();
                    }
                  }}
                >
                  <select
                    aria-label="Case document"
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
                <QuickForm
                  label="Comment"
                  value={comment}
                  placeholder="Comment"
                  onChange={setComment}
                  onSubmit={() => {
                    commentMutation.mutate();
                  }}
                />
                <QuickForm
                  label="Task"
                  value={taskTitle}
                  placeholder="Task title"
                  onChange={setTaskTitle}
                  onSubmit={() => {
                    taskMutation.mutate();
                  }}
                />
                <form
                  className="work-stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (decisionType.trim() !== "" && rationale.trim() !== "") {
                      decisionMutation.mutate();
                    }
                  }}
                >
                  <input
                    aria-label="Decision type"
                    placeholder="Decision type"
                    value={decisionType}
                    onChange={(event) => {
                      setDecisionType(event.target.value);
                    }}
                  />
                  <textarea
                    aria-label="Rationale"
                    placeholder="Rationale"
                    value={rationale}
                    onChange={(event) => {
                      setRationale(event.target.value);
                    }}
                  />
                  <button className="button" type="submit">
                    Add decision
                  </button>
                </form>
                <CaseDetailLists detail={detailQuery.data} />
              </>
            )}
          </aside>
        </div>
      </div>
    </PageContainer>
  );
}

function QuickForm({
  label,
  value,
  placeholder,
  onChange,
  onSubmit,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <form
      className="work-stack-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim() !== "") {
          onSubmit();
        }
      }}
    >
      <input
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <button className="button" type="submit">
        Add {label.toLowerCase()}
      </button>
    </form>
  );
}

function CaseDetailLists({ detail }: { detail: Awaited<ReturnType<typeof getCase>> | undefined }) {
  if (detail === undefined) {
    return <p className="work-empty">Loading details.</p>;
  }
  return (
    <div className="work-subgrid">
      <ListBlock title="Documents" items={detail.documents.map((item) => item.document_id)} />
      <ListBlock title="Comments" items={detail.comments.map((item) => item.body)} />
      <ListBlock
        title="Tasks"
        items={detail.tasks.map((item) => `${item.title} (${item.status})`)}
      />
      <ListBlock
        title="Decisions"
        items={detail.decisions.map((item) => `${item.decision_type}: ${item.rationale}`)}
      />
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="work-list-block" aria-label={title}>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="work-empty">None</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
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

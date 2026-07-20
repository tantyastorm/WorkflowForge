import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "../../components/feedback/ErrorState";
import { LoadingState } from "../../components/feedback/LoadingState";
import { PageContainer } from "../../components/layout/PageContainer";
import { ApiError } from "../../lib/api-client";
import { DependencyStatusCard } from "./DependencyStatusCard";
import { SystemStatusSummary } from "./SystemStatusSummary";
import {
  apiLivenessQueryOptions,
  apiReadinessQueryOptions,
  dependencyHealthQueryOptions,
} from "./queries";
import { dependencyMetadata, getOverallStatus } from "./status-utils";

export function SystemStatusPage() {
  const liveQuery = useQuery(apiLivenessQueryOptions());
  const readyQuery = useQuery(apiReadinessQueryOptions());
  const dependenciesQuery = useQuery(dependencyHealthQueryOptions());

  const queries = [liveQuery, readyQuery, dependenciesQuery];
  const isInitialLoading = queries.every((query) => query.isPending);
  const isRefreshing = queries.some((query) => query.isRefetching);

  async function handleRefresh() {
    if (isRefreshing) {
      return;
    }
    await Promise.all(queries.map((query) => query.refetch()));
  }

  if (isInitialLoading) {
    return (
      <PageContainer>
        <div className="status-page status-page--loading">
          <h1>System status</h1>
          <LoadingState message="Checking platform status" />
        </div>
      </PageContainer>
    );
  }

  const overallStatus = getOverallStatus({
    live: liveQuery.data,
    liveError: liveQuery.isError,
    ready: readyQuery.data,
    dependencyHealth: dependenciesQuery.data,
    dependencyError: dependenciesQuery.isError,
  });

  const liveErrorMessage = liveQuery.error ? readableError(liveQuery.error) : undefined;
  const readyErrorMessage = readyQuery.error ? readableError(readyQuery.error) : undefined;
  const dependencyErrorMessage = dependenciesQuery.error
    ? readableError(dependenciesQuery.error)
    : undefined;

  return (
    <PageContainer>
      <div className="status-page">
        <header className="status-page__header">
          <div>
            <p className="status-page__eyebrow">Operations</p>
            <h1>System status</h1>
            <p>
              Live shows whether the API process responds. Ready shows whether startup completed.
            </p>
          </div>
          <button
            className="button status-page__refresh"
            type="button"
            onClick={() => void handleRefresh()}
            disabled={isRefreshing}
          >
            {isRefreshing ? "Refreshing" : "Refresh status"}
          </button>
        </header>

        <SystemStatusSummary
          overallStatus={overallStatus}
          liveness={liveQuery.data}
          readiness={readyQuery.data}
          dependencyHealth={dependenciesQuery.data}
          livenessError={liveErrorMessage}
          readinessError={readyErrorMessage}
          dependencyError={dependencyErrorMessage}
        />

        {liveQuery.isError ? (
          <ErrorState
            title="API unavailable"
            message={liveErrorMessage ?? "The API liveness check could not complete."}
            actionLabel="Retry"
            onRetry={() => void handleRefresh()}
          />
        ) : null}

        <section className="status-section" aria-labelledby="api-status-heading">
          <h2 id="api-status-heading">API</h2>
          <div className="status-grid status-grid--api">
            <ApiStatusCard
              label="API liveness"
              description="API process responds"
              state={liveQuery.data?.status === "ok" ? "Healthy" : "Unknown"}
              error={liveErrorMessage}
            />
            <ApiStatusCard
              label="API readiness"
              description="Startup completed"
              state={
                readyQuery.data?.status === "ready"
                  ? "Healthy"
                  : readyQuery.data?.status === "not_ready"
                    ? "Unavailable"
                    : "Unknown"
              }
              error={readyErrorMessage}
            />
          </div>
        </section>

        <section className="status-section" aria-labelledby="dependency-status-heading">
          <h2 id="dependency-status-heading">Dependencies</h2>
          {dependenciesQuery.isError ? (
            <p className="status-page__warning" role="status">
              Dependency status is unknown. {dependencyErrorMessage}
            </p>
          ) : null}
          <div className="status-grid">
            {dependencyMetadata.map((metadata) => (
              <DependencyStatusCard
                key={metadata.key}
                metadata={metadata}
                health={dependenciesQuery.data?.dependencies[metadata.key]}
              />
            ))}
          </div>
        </section>
      </div>
    </PageContainer>
  );
}

function ApiStatusCard({
  label,
  description,
  state,
  error,
}: {
  label: string;
  description: string;
  state: "Healthy" | "Unavailable" | "Unknown";
  error: string | undefined;
}) {
  const badgeState =
    state === "Healthy" ? "healthy" : state === "Unavailable" ? "unhealthy" : "unknown";

  return (
    <article className="status-card" aria-label={label}>
      <div className="status-card__header">
        <div>
          <h3>{label}</h3>
          <p>{description}</p>
        </div>
        <span className={`status-badge status-badge--${badgeState}`}>
          <span className="status-badge__dot" aria-hidden="true" />
          {state}
        </span>
      </div>
      {error !== undefined ? <p className="status-card__error">{error}</p> : null}
    </article>
  );
}

function readableError(error: Error): string {
  if (error instanceof ApiError) {
    const correlation =
      error.correlationId === null ? "" : ` Correlation ID: ${error.correlationId}.`;
    if (error.code === "INVALID_RESPONSE") {
      return `Health response was malformed.${correlation}`;
    }
    if (error.timeout) {
      return `Request timed out.${correlation}`;
    }
    return `Request failed.${correlation}`;
  }
  return "Request failed.";
}

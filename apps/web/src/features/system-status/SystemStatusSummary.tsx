import { formatCheckedAt } from "./status-utils";
import type { ApiLiveness, ApiReadiness, DependencyHealth } from "./types";

type SystemStatusSummaryProps = {
  overallStatus: string;
  liveness: ApiLiveness | undefined;
  readiness: ApiReadiness | undefined;
  dependencyHealth: DependencyHealth | undefined;
  livenessError: string | undefined;
  readinessError: string | undefined;
  dependencyError: string | undefined;
};

export function SystemStatusSummary({
  overallStatus,
  liveness,
  readiness,
  dependencyHealth,
  livenessError,
  readinessError,
  dependencyError,
}: SystemStatusSummaryProps) {
  const liveStatus =
    livenessError ?? (liveness?.status === "ok" ? "API process responds" : "Unknown");
  const readyStatus =
    readinessError ??
    (readiness?.status === "ready"
      ? "Startup completed"
      : readiness?.status === "not_ready"
        ? "Startup not complete"
        : "Unknown");

  return (
    <section className="status-summary" aria-labelledby="system-status-summary">
      <div>
        <p className="status-summary__eyebrow">Platform status</p>
        <h2 id="system-status-summary">{overallStatus}</h2>
        {dependencyHealth !== undefined ? (
          <p>Dependency checks completed {formatCheckedAt(dependencyHealth.checked_at)}.</p>
        ) : (
          <p>Dependency check time is unavailable.</p>
        )}
      </div>
      <div className="status-summary__checks" aria-label="API checks">
        <div className="status-summary__check">
          <span>API liveness</span>
          <strong>{liveStatus}</strong>
        </div>
        <div className="status-summary__check">
          <span>API readiness</span>
          <strong>{readyStatus}</strong>
        </div>
        {dependencyError !== undefined ? (
          <div className="status-summary__check status-summary__check--wide">
            <span>Dependencies</span>
            <strong>{dependencyError}</strong>
          </div>
        ) : null}
      </div>
    </section>
  );
}

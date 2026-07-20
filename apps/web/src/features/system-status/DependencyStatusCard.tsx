import {
  dependencyStatusLabel,
  formatLatency,
  type DependencyDisplayMetadata,
} from "./status-utils";
import type { DependencyHealthItem } from "./types";

type DependencyStatusCardProps = {
  metadata: DependencyDisplayMetadata;
  health: DependencyHealthItem | undefined;
};

export function DependencyStatusCard({ metadata, health }: DependencyStatusCardProps) {
  const state = health?.status ?? "unknown";
  const stateLabel = health === undefined ? "Unknown" : dependencyStatusLabel(health.status);

  return (
    <article className="status-card" aria-labelledby={`dependency-${metadata.key}`}>
      <div className="status-card__header">
        <div>
          <h3 id={`dependency-${metadata.key}`}>{metadata.label}</h3>
          <p>{metadata.description}</p>
        </div>
        <span className={`status-badge status-badge--${state}`}>
          <span className="status-badge__dot" aria-hidden="true" />
          {stateLabel}
        </span>
      </div>
      <dl className="status-card__details">
        <div>
          <dt>Latency</dt>
          <dd>{health === undefined ? "Unavailable" : formatLatency(health.latency_ms)}</dd>
        </div>
        {health?.detail !== undefined && health.detail !== null ? (
          <div>
            <dt>Detail</dt>
            <dd>{health.detail}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

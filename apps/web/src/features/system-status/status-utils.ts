import type {
  ApiLiveness,
  ApiReadiness,
  DependencyHealth,
  DependencyName,
  DependencyStatus,
} from "./types";

export type DependencyDisplayMetadata = {
  key: DependencyName;
  label: string;
  description: string;
};

export const dependencyMetadata: readonly DependencyDisplayMetadata[] = [
  {
    key: "postgresql",
    label: "PostgreSQL",
    description: "durable application state",
  },
  {
    key: "redis",
    label: "Redis",
    description: "queues and transient coordination",
  },
  {
    key: "object_storage",
    label: "Object storage",
    description: "documents and artifacts",
  },
  {
    key: "worker",
    label: "Worker",
    description: "asynchronous task execution",
  },
  {
    key: "scheduler",
    label: "Scheduler",
    description: "periodic task publication",
  },
];

export function formatCheckedAt(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function formatLatency(latencyMs: number): string {
  if (latencyMs < 10) {
    return `${latencyMs.toFixed(1)} ms`;
  }
  return `${String(Math.round(latencyMs))} ms`;
}

export function dependencyStatusLabel(status: DependencyStatus): string {
  return status === "healthy" ? "Healthy" : "Unhealthy";
}

export function getOverallStatus(params: {
  live: ApiLiveness | undefined;
  liveError: boolean;
  ready: ApiReadiness | undefined;
  dependencyHealth: DependencyHealth | undefined;
  dependencyError: boolean;
}): "All systems operational" | "Platform degraded" | "API unavailable" | "Status unknown" {
  if (params.liveError) {
    return "API unavailable";
  }
  if (params.dependencyError || params.dependencyHealth === undefined) {
    return "Status unknown";
  }
  if (params.ready?.status === "not_ready" || params.dependencyHealth.status === "unhealthy") {
    return "Platform degraded";
  }
  return "All systems operational";
}

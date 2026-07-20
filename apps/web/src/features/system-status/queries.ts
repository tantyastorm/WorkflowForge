import { queryOptions } from "@tanstack/react-query";

import { getApiLiveness, getApiReadiness, getDependencyHealth } from "./api";

const HEALTH_REFETCH_INTERVAL_MS = 20_000;
const HEALTH_STALE_TIME_MS = 5_000;
const HEALTH_RETRY_DELAY_MS = 100;

export const healthQueryKeys = {
  live: ["health", "live"] as const,
  ready: ["health", "ready"] as const,
  dependencies: ["health", "dependencies"] as const,
};

export function apiLivenessQueryOptions() {
  return queryOptions({
    queryKey: healthQueryKeys.live,
    queryFn: () => getApiLiveness(),
    refetchInterval: HEALTH_REFETCH_INTERVAL_MS,
    retry: 1,
    retryDelay: HEALTH_RETRY_DELAY_MS,
    staleTime: HEALTH_STALE_TIME_MS,
  });
}

export function apiReadinessQueryOptions() {
  return queryOptions({
    queryKey: healthQueryKeys.ready,
    queryFn: () => getApiReadiness(),
    refetchInterval: HEALTH_REFETCH_INTERVAL_MS,
    retry: 1,
    retryDelay: HEALTH_RETRY_DELAY_MS,
    staleTime: HEALTH_STALE_TIME_MS,
  });
}

export function dependencyHealthQueryOptions() {
  return queryOptions({
    queryKey: healthQueryKeys.dependencies,
    queryFn: () => getDependencyHealth(),
    refetchInterval: HEALTH_REFETCH_INTERVAL_MS,
    retry: 1,
    retryDelay: HEALTH_RETRY_DELAY_MS,
    staleTime: HEALTH_STALE_TIME_MS,
  });
}

import { z, ZodError } from "zod";

import { ApiClient, ApiError, createApiClient } from "../../lib/api-client";
import {
  apiLivenessSchema,
  apiReadinessSchema,
  dependencyHealthSchema,
  type ApiLiveness,
  type ApiReadiness,
  type DependencyHealth,
} from "./types";

const HEALTH_TIMEOUT_MS = 5_000;

export async function getApiLiveness(client: ApiClient = createApiClient()): Promise<ApiLiveness> {
  const response = await client.request<unknown>("/health/live", {
    timeoutMs: HEALTH_TIMEOUT_MS,
  });
  return parseHealthResponse(apiLivenessSchema, response.data, response.correlationId);
}

export async function getApiReadiness(
  client: ApiClient = createApiClient(),
): Promise<ApiReadiness> {
  const response = await client.request<unknown>("/health/ready", {
    expectedStatuses: [200, 503],
    timeoutMs: HEALTH_TIMEOUT_MS,
  });
  return parseHealthResponse(apiReadinessSchema, response.data, response.correlationId);
}

export async function getDependencyHealth(
  client: ApiClient = createApiClient(),
): Promise<DependencyHealth> {
  const response = await client.request<unknown>("/health/dependencies", {
    expectedStatuses: [200, 503],
    timeoutMs: HEALTH_TIMEOUT_MS,
  });
  return parseHealthResponse(dependencyHealthSchema, response.data, response.correlationId);
}

function parseHealthResponse<T>(
  schema: z.ZodType<T>,
  data: unknown,
  correlationId: string | null,
): T {
  try {
    return schema.parse(data);
  } catch (error) {
    if (error instanceof ZodError) {
      throw new ApiError({
        status: null,
        code: "INVALID_RESPONSE",
        message: "Health response was malformed.",
        correlationId,
      });
    }
    throw error;
  }
}

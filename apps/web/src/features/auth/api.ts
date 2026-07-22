import { z, ZodError } from "zod";

import { ApiClient, ApiError, apiClient } from "../../lib/api-client";
import {
  logoutAllResponseSchema,
  logoutResponseSchema,
  meResponseSchema,
  tenantContextSchema,
  tokenResponseSchema,
  userOrganizationSchema,
  type MeResponse,
  type TenantContext,
  type TokenResponse,
  type UserOrganization,
} from "./types";

const organizationListSchema = z.array(userOrganizationSchema);

export async function loginWithPassword(
  payload: { email: string; password: string },
  client: ApiClient = apiClient,
): Promise<TokenResponse> {
  const response = await client.request<unknown>("/api/v1/auth/login", {
    method: "POST",
    body: payload,
    credentials: "include",
  });
  return parseApiResponse(tokenResponseSchema, response.data, response.correlationId);
}

export async function refreshAccessToken(client: ApiClient = apiClient): Promise<TokenResponse> {
  const response = await client.request<unknown>("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
    csrf: true,
    retryOnUnauthorized: false,
  });
  return parseApiResponse(tokenResponseSchema, response.data, response.correlationId);
}

export async function getCurrentUser(client: ApiClient = apiClient): Promise<MeResponse> {
  const response = await client.request<unknown>("/api/v1/auth/me", {
    authenticated: true,
  });
  return parseApiResponse(meResponseSchema, response.data, response.correlationId);
}

export async function listUserOrganizations(
  client: ApiClient = apiClient,
): Promise<UserOrganization[]> {
  const response = await client.request<unknown>("/api/v1/auth/organizations", {
    authenticated: true,
  });
  return parseApiResponse(organizationListSchema, response.data, response.correlationId);
}

export async function getTenantContext(
  organizationId: string,
  client: ApiClient = apiClient,
): Promise<TenantContext> {
  const response = await client.request<unknown>(
    `/api/v1/organizations/${encodeURIComponent(organizationId)}/tenancy/context`,
    {
      authenticated: true,
    },
  );
  return parseApiResponse(tenantContextSchema, response.data, response.correlationId);
}

export async function logoutSession(client: ApiClient = apiClient): Promise<void> {
  const response = await client.request<unknown>("/api/v1/auth/logout", {
    method: "POST",
    authenticated: true,
    credentials: "include",
    csrf: true,
    retryOnUnauthorized: false,
  });
  parseApiResponse(logoutResponseSchema, response.data, response.correlationId);
}

export async function logoutAllSessions(client: ApiClient = apiClient): Promise<number> {
  const response = await client.request<unknown>("/api/v1/auth/logout-all", {
    method: "POST",
    authenticated: true,
    credentials: "include",
    csrf: true,
    retryOnUnauthorized: false,
  });
  return parseApiResponse(logoutAllResponseSchema, response.data, response.correlationId)
    .revoked_sessions;
}

function parseApiResponse<T>(schema: z.ZodType<T>, data: unknown, correlationId: string | null): T {
  try {
    return schema.parse(data);
  } catch (error) {
    if (error instanceof ZodError) {
      throw new ApiError({
        status: null,
        code: "INVALID_RESPONSE",
        message: "API response was malformed.",
        correlationId,
      });
    }
    throw error;
  }
}

/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, apiClient } from "../../lib/api-client";
import {
  getCurrentUser,
  getTenantContext,
  listUserOrganizations,
  loginWithPassword,
  logoutAllSessions,
  logoutSession,
  refreshAccessToken,
} from "./api";
import type { MeResponse, Permission, TenantContext, UserOrganization } from "./types";

const SELECTED_ORGANIZATION_KEY = "workflowforge.selectedOrganizationId";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type AuthStatus = "initializing" | "anonymous" | "authenticated" | "authenticating" | "error";

export type AuthState = {
  status: AuthStatus;
  user: MeResponse | null;
  organizations: UserOrganization[];
  selectedOrganizationId: string | null;
  tenantContext: TenantContext | null;
  accessTokenExpiresAt: string | null;
  error: AuthUiError | null;
};

export type AuthUiError = {
  title: string;
  message: string;
  status: number | null;
  code: string;
  retryAfterSeconds: number | null;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<void>;
  refresh: () => Promise<string | null>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<number>;
  selectOrganization: (organizationId: string) => Promise<void>;
  hasPermission: (permission: Permission) => boolean;
  clearError: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const anonymousState: AuthState = {
  status: "anonymous",
  user: null,
  organizations: [],
  selectedOrganizationId: null,
  tenantContext: null,
  accessTokenExpiresAt: null,
  error: null,
};

export function AuthProvider({
  children,
  restoreSessionOnMount = true,
}: {
  children: ReactNode;
  restoreSessionOnMount?: boolean;
}) {
  const [state, setState] = useState<AuthState>({ ...anonymousState, status: "initializing" });
  const accessTokenRef = useRef<string | null>(null);
  const accessTokenExpiresAtRef = useRef<string | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);
  const generationRef = useRef(0);

  const clearSession = useCallback(() => {
    generationRef.current += 1;
    accessTokenRef.current = null;
    accessTokenExpiresAtRef.current = null;
    refreshPromiseRef.current = null;
    safeRemoveSelectedOrganization();
    setState(anonymousState);
  }, []);

  const loadSession = useCallback(async (accessToken: string, accessTokenExpiresAt: string) => {
    const generation = generationRef.current;
    accessTokenRef.current = accessToken;
    accessTokenExpiresAtRef.current = accessTokenExpiresAt;
    const [user, organizations] = await Promise.all([getCurrentUser(), listUserOrganizations()]);
    if (generation !== generationRef.current) {
      return;
    }
    const storedOrganizationId = safeGetSelectedOrganization();
    const selectedOrganization =
      organizations.find((organization) => organization.id === storedOrganizationId) ??
      organizations[0] ??
      null;
    const tenantContext =
      selectedOrganization === null ? null : await getTenantContext(selectedOrganization.id);
    if (generation !== generationRef.current) {
      return;
    }
    if (tenantContext !== null && tenantContext.organization_id !== selectedOrganization?.id) {
      accessTokenRef.current = null;
      accessTokenExpiresAtRef.current = null;
      safeRemoveSelectedOrganization();
      setState({
        ...anonymousState,
        status: "error",
        error: {
          title: "Session restoration failed",
          message: "The selected organization context could not be verified.",
          status: null,
          code: "TENANT_CONTEXT_MISMATCH",
          retryAfterSeconds: null,
        },
      });
      return;
    }

    if (selectedOrganization === null) {
      safeRemoveSelectedOrganization();
    } else {
      safeSetSelectedOrganization(selectedOrganization.id);
    }
    accessTokenRef.current = accessToken;
    accessTokenExpiresAtRef.current = accessTokenExpiresAt;

    setState({
      status: "authenticated",
      user,
      organizations,
      selectedOrganizationId: selectedOrganization?.id ?? null,
      tenantContext,
      accessTokenExpiresAt,
      error: null,
    });
  }, []);

  const refresh = useCallback(async (): Promise<string | null> => {
    if (refreshPromiseRef.current !== null) {
      return refreshPromiseRef.current;
    }
    const generation = generationRef.current;
    const pendingRefresh = refreshAccessToken()
      .then((token) => {
        if (generation !== generationRef.current) {
          return null;
        }
        accessTokenRef.current = token.access_token;
        accessTokenExpiresAtRef.current = token.access_token_expires_at;
        setState((current) => ({
          ...current,
          accessTokenExpiresAt: token.access_token_expires_at,
          error: null,
        }));
        return token.access_token;
      })
      .catch((error: unknown) => {
        if (generation !== generationRef.current) {
          return null;
        }
        accessTokenRef.current = null;
        accessTokenExpiresAtRef.current = null;
        if (isRefreshAuthenticationFailure(error)) {
          setState(anonymousState);
          return null;
        }
        setState((current) => ({
          ...current,
          status: "error",
          error: toUiError(error, "Session refresh failed"),
        }));
        return null;
      })
      .finally(() => {
        if (refreshPromiseRef.current === pendingRefresh) {
          refreshPromiseRef.current = null;
        }
      });
    refreshPromiseRef.current = pendingRefresh;
    return refreshPromiseRef.current;
  }, []);

  useEffect(() => {
    apiClient.setAccessTokenProvider(() => accessTokenRef.current);
    apiClient.setRefreshHandler(refresh);
    return () => {
      apiClient.setAccessTokenProvider(null);
      apiClient.setRefreshHandler(null);
    };
  }, [refresh]);

  useEffect(() => {
    if (!restoreSessionOnMount) {
      setState(anonymousState);
      return;
    }
    let active = true;
    async function restoreSession() {
      const token = await refresh();
      if (!active) {
        return;
      }
      if (token === null) {
        accessTokenRef.current = null;
        accessTokenExpiresAtRef.current = null;
        setState(anonymousState);
        return;
      }
      try {
        const accessTokenExpiresAt = accessTokenExpiresAtRef.current;
        if (accessTokenExpiresAt === null) {
          throw new Error("Refreshed token was missing expiry metadata.");
        }
        await loadSession(token, accessTokenExpiresAt);
      } catch (error) {
        accessTokenRef.current = null;
        accessTokenExpiresAtRef.current = null;
        safeRemoveSelectedOrganization();
        setState({
          ...anonymousState,
          status: isRefreshAuthenticationFailure(error) ? "anonymous" : "error",
          error: isRefreshAuthenticationFailure(error)
            ? null
            : toUiError(error, "Session restoration failed"),
        });
      }
    }
    void restoreSession();
    return () => {
      active = false;
    };
  }, [loadSession, refresh, restoreSessionOnMount]);

  const login = useCallback(
    async (email: string, password: string) => {
      setState((current) => ({ ...current, status: "authenticating", error: null }));
      try {
        const token = await loginWithPassword({ email, password });
        generationRef.current += 1;
        refreshPromiseRef.current = null;
        accessTokenRef.current = token.access_token;
        await loadSession(token.access_token, token.access_token_expires_at);
      } catch (error) {
        accessTokenRef.current = null;
        accessTokenExpiresAtRef.current = null;
        setState({
          ...anonymousState,
          status: "anonymous",
          error: toUiError(error, "Sign in failed"),
        });
        throw error;
      }
    },
    [loadSession],
  );

  const selectOrganization = useCallback(async (organizationId: string) => {
    generationRef.current += 1;
    refreshPromiseRef.current = null;
    setState((current) => ({
      ...current,
      selectedOrganizationId: organizationId,
      tenantContext: null,
      error: null,
    }));
    try {
      const tenantContext = await getTenantContext(organizationId);
      if (tenantContext.organization_id !== organizationId) {
        safeRemoveSelectedOrganization();
        throw new ApiError({
          status: null,
          code: "TENANT_CONTEXT_MISMATCH",
          message: "Tenant context organization mismatch.",
        });
      }
      safeSetSelectedOrganization(organizationId);
      setState((current) => ({
        ...current,
        selectedOrganizationId: organizationId,
        tenantContext,
        status: "authenticated",
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        selectedOrganizationId: null,
        tenantContext: null,
        error: toUiError(error, "Organization selection failed"),
      }));
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } catch {
      // Local logout is authoritative for the browser even if the API call fails.
    }
    clearSession();
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    try {
      const revokedSessions = await logoutAllSessions();
      clearSession();
      return revokedSessions;
    } catch {
      clearSession();
      return 0;
    }
  }, [clearSession]);

  const hasPermission = useCallback(
    (permission: Permission) => state.tenantContext?.permissions.includes(permission) ?? false,
    [state.tenantContext],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      refresh,
      logout,
      logoutAll,
      selectOrganization,
      hasPermission,
      clearError: () => {
        setState((current) => ({ ...current, error: null }));
      },
    }),
    [hasPermission, login, logout, logoutAll, refresh, selectOrganization, state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}

function isAuthenticationFailure(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function isRefreshAuthenticationFailure(error: unknown): boolean {
  return (
    isAuthenticationFailure(error) ||
    (error instanceof ApiError && error.status === 403 && error.code === "csrf_failed")
  );
}

function toUiError(error: unknown, title: string): AuthUiError {
  if (error instanceof ApiError) {
    return {
      title,
      message: messageForApiError(error),
      status: error.status,
      code: error.code,
      retryAfterSeconds: error.retryAfterSeconds,
    };
  }
  return {
    title,
    message: "The request could not be completed.",
    status: null,
    code: "UNKNOWN_ERROR",
    retryAfterSeconds: null,
  };
}

function messageForApiError(error: ApiError): string {
  if (error.status === 401) {
    return "Your session has expired. Sign in again to continue.";
  }
  if (error.status === 403) {
    return "You do not have access to that organization or action.";
  }
  if (error.status === 422) {
    return "The request contained invalid data.";
  }
  if (error.status === 429) {
    const suffix =
      error.retryAfterSeconds === null
        ? ""
        : ` Try again in ${String(error.retryAfterSeconds)} seconds.`;
    return `Too many attempts.${suffix}`;
  }
  if (error.timeout || error.code === "NETWORK_ERROR") {
    return "WorkflowForge is unreachable. Check the API connection and try again.";
  }
  return "WorkflowForge could not complete the request.";
}

function safeGetSelectedOrganization(): string | null {
  try {
    const value = localStorage.getItem(SELECTED_ORGANIZATION_KEY);
    if (value === null) {
      return null;
    }
    if (!UUID_PATTERN.test(value)) {
      safeRemoveSelectedOrganization();
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

function safeSetSelectedOrganization(organizationId: string): void {
  if (!UUID_PATTERN.test(organizationId)) {
    safeRemoveSelectedOrganization();
    return;
  }
  try {
    localStorage.setItem(SELECTED_ORGANIZATION_KEY, organizationId);
  } catch {
    // Selection persistence is a convenience; authorization always comes from the API.
  }
}

function safeRemoveSelectedOrganization(): void {
  try {
    localStorage.removeItem(SELECTED_ORGANIZATION_KEY);
  } catch {
    // Ignore unavailable storage in private or restricted browser contexts.
  }
}

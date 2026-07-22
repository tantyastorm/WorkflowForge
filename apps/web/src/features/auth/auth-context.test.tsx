import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ApiError } from "../../lib/api-client";
import { renderWithProviders } from "../../test/render";
import {
  getCurrentUser,
  getTenantContext,
  listUserOrganizations,
  logoutSession,
  refreshAccessToken,
} from "./api";
import { AuthProvider, useAuth } from "./auth-context";
import type { TenantContext, UserOrganization } from "./types";

vi.mock("./api", () => ({
  refreshAccessToken: vi.fn(),
  getCurrentUser: vi.fn(),
  getTenantContext: vi.fn(),
  listUserOrganizations: vi.fn(),
  loginWithPassword: vi.fn(),
  logoutAllSessions: vi.fn(),
  logoutSession: vi.fn(),
}));

const refreshAccessTokenMock = vi.mocked(refreshAccessToken);
const getCurrentUserMock = vi.mocked(getCurrentUser);
const getTenantContextMock = vi.mocked(getTenantContext);
const listUserOrganizationsMock = vi.mocked(listUserOrganizations);
const logoutSessionMock = vi.mocked(logoutSession);

const USER_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "44444444-4444-4444-8444-444444444444";
const ORG_A_ID = "22222222-2222-4222-8222-222222222222";
const ORG_B_ID = "22222222-2222-4222-8222-333333333333";
const MEMBERSHIP_ID = "33333333-3333-4333-8333-333333333333";
const SELECTED_ORGANIZATION_KEY = "workflowforge.selectedOrganizationId";

function RefreshProbe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="selected">{auth.selectedOrganizationId ?? "none"}</span>
      <span data-testid="context">{auth.tenantContext?.organization_id ?? "none"}</span>
      <button
        type="button"
        onClick={() => {
          void Promise.all([auth.refresh(), auth.refresh()]);
        }}
      >
        Refresh twice
      </button>
      <button
        type="button"
        onClick={() => {
          void auth.logout();
        }}
      >
        Sign out
      </button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getCurrentUserMock.mockResolvedValue({
      user_id: USER_ID,
      session_id: SESSION_ID,
      issued_at: "2026-01-02T03:04:05Z",
      expires_at: "2026-01-02T03:19:05Z",
    });
    listUserOrganizationsMock.mockResolvedValue([organization(ORG_A_ID), organization(ORG_B_ID)]);
    getTenantContextMock.mockImplementation((organizationId) =>
      Promise.resolve(tenantContext(organizationId)),
    );
    logoutSessionMock.mockResolvedValue();
  });

  it("deduplicates concurrent refresh calls", async () => {
    refreshAccessTokenMock.mockResolvedValue({
      access_token: "access-1",
      token_type: "Bearer",
      access_token_expires_at: "2026-01-02T03:19:05Z",
      session_id: "44444444-4444-4444-8444-444444444444",
    });
    const user = userEvent.setup();

    renderWithProviders(<RefreshProbe />);
    await user.click(screen.getByRole("button", { name: "Refresh twice" }));

    expect(refreshAccessTokenMock).toHaveBeenCalledTimes(1);
  });

  it("restores a valid session and revalidates the stored organization", async () => {
    localStorage.setItem(SELECTED_ORGANIZATION_KEY, ORG_B_ID);
    refreshAccessTokenMock.mockResolvedValue(tokenResponse("access-1"));

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("selected")).toHaveTextContent(ORG_B_ID);
    expect(screen.getByTestId("context")).toHaveTextContent(ORG_B_ID);
    expect(refreshAccessTokenMock).toHaveBeenCalledTimes(1);
    expect(getCurrentUserMock).toHaveBeenCalledTimes(1);
    expect(listUserOrganizationsMock).toHaveBeenCalledTimes(1);
    expect(getTenantContextMock).toHaveBeenCalledWith(ORG_B_ID);
  });

  it("removes malformed stored organization IDs and falls back to an active organization", async () => {
    localStorage.setItem(SELECTED_ORGANIZATION_KEY, "not-a-uuid");
    refreshAccessTokenMock.mockResolvedValue(tokenResponse("access-1"));

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("selected")).toHaveTextContent(ORG_A_ID);
    });
    expect(localStorage.getItem(SELECTED_ORGANIZATION_KEY)).toBe(ORG_A_ID);
  });

  it("does not crash when localStorage is unavailable during restoration", async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    refreshAccessTokenMock.mockResolvedValue(tokenResponse("access-1"));

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("selected")).toHaveTextContent(ORG_A_ID);
    getItemSpy.mockRestore();
    setItemSpy.mockRestore();
  });

  it("keeps logout authoritative when a refresh resolves later", async () => {
    const deferred = deferredPromise<Awaited<ReturnType<typeof refreshAccessToken>>>();
    refreshAccessTokenMock.mockReturnValue(deferred.promise);
    const user = userEvent.setup();

    renderWithProviders(<RefreshProbe />);
    await user.click(screen.getByRole("button", { name: "Refresh twice" }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    deferred.resolve(tokenResponse("late-access"));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    });
    expect(screen.getByTestId("context")).toHaveTextContent("none");
  });

  it("clears local state even when logout fails", async () => {
    logoutSessionMock.mockRejectedValue(
      new ApiError({
        status: 403,
        code: "csrf_failed",
        message: "CSRF validation failed.",
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<RefreshProbe />);
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    });
    expect(screen.getByTestId("context")).toHaveTextContent("none");
  });

  it("does not persist access tokens in browser storage", async () => {
    refreshAccessTokenMock.mockResolvedValue(tokenResponse("sensitive-access-token"));

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(JSON.stringify(localStorage)).not.toContain("sensitive-access-token");
    expect(JSON.stringify(sessionStorage)).not.toContain("sensitive-access-token");
  });

  it("clears auth state when restoration refresh is expired or missing CSRF", async () => {
    refreshAccessTokenMock.mockRejectedValue(
      new ApiError({
        status: 403,
        code: "csrf_failed",
        message: "CSRF validation failed.",
      }),
    );

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    });
    expect(getCurrentUserMock).not.toHaveBeenCalled();
  });

  it("rejects tenant context mismatches instead of reusing stale permissions", async () => {
    refreshAccessTokenMock.mockResolvedValue(tokenResponse("access-1"));
    getTenantContextMock.mockResolvedValue(tenantContext(ORG_B_ID));

    render(
      <AuthProvider>
        <RefreshProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("error");
    });
    expect(screen.getByTestId("context")).toHaveTextContent("none");
    expect(localStorage.getItem(SELECTED_ORGANIZATION_KEY)).toBeNull();
  });
});

function tokenResponse(accessToken: string) {
  return {
    access_token: accessToken,
    token_type: "Bearer" as const,
    access_token_expires_at: "2026-01-02T03:19:05Z",
    session_id: SESSION_ID,
  };
}

function organization(organizationId: string): UserOrganization {
  return {
    id: organizationId,
    name: organizationId === ORG_A_ID ? "Alpha Operations" : "Beta Operations",
    slug: organizationId === ORG_A_ID ? "alpha" : "beta",
    membership_id: MEMBERSHIP_ID,
    membership_role: "owner",
    membership_status: "active",
  };
}

function tenantContext(organizationId: string): TenantContext {
  return {
    user_id: USER_ID,
    organization_id: organizationId,
    membership_id: MEMBERSHIP_ID,
    role: "owner",
    permissions: ["organization.read", "security.manage"],
  };
}

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { useAuth } from "./auth-context";
import { LoginPage } from "./LoginPage";

vi.mock("./auth-context", () => ({
  useAuth: vi.fn(),
}));

const useAuthMock = vi.mocked(useAuth);

describe("LoginPage", () => {
  it("renders accessible credentials fields and safe retry-after errors", () => {
    useAuthMock.mockReturnValue({
      status: "anonymous",
      user: null,
      organizations: [],
      selectedOrganizationId: null,
      tenantContext: null,
      accessTokenExpiresAt: null,
      error: {
        title: "Sign in failed",
        message: "Too many attempts. Try again in 42 seconds.",
        status: 429,
        code: "rate_limited",
        retryAfterSeconds: 42,
      },
      login: vi.fn(),
      refresh: vi.fn(),
      logout: vi.fn(),
      logoutAll: vi.fn(),
      selectOrganization: vi.fn(),
      hasPermission: vi.fn(),
      clearError: vi.fn(),
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again in 42 seconds.",
    );
  });
});

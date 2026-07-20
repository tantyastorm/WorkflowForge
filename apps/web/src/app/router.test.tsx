import { screen } from "@testing-library/react";

import { renderApp } from "../test/render";
import {
  getApiLiveness,
  getApiReadiness,
  getDependencyHealth,
} from "../features/system-status/api";

vi.mock("../features/system-status/api", () => ({
  getApiLiveness: vi.fn(),
  getApiReadiness: vi.fn(),
  getDependencyHealth: vi.fn(),
}));

const getApiLivenessMock = vi.mocked(getApiLiveness);
const getApiReadinessMock = vi.mocked(getApiReadiness);
const getDependencyHealthMock = vi.mocked(getDependencyHealth);

beforeEach(() => {
  getApiLivenessMock.mockResolvedValue({ status: "ok", service: "api" });
  getApiReadinessMock.mockResolvedValue({ status: "ready", service: "api" });
  getDependencyHealthMock.mockResolvedValue({
    status: "healthy",
    checked_at: "2026-07-20T10:30:00Z",
    dependencies: {
      postgresql: { status: "healthy", latency_ms: 4.2, detail: null },
      redis: { status: "healthy", latency_ms: 2, detail: null },
      object_storage: { status: "healthy", latency_ms: 12.5, detail: null },
      worker: { status: "healthy", latency_ms: 25, detail: "1 worker responded." },
      scheduler: { status: "healthy", latency_ms: 3.8, detail: null },
    },
  });
});

describe("router", () => {
  it("renders the home route", () => {
    renderApp({ route: "/" });

    expect(screen.getByRole("heading", { name: "WorkflowForge" })).toBeInTheDocument();
  });

  it("renders the system status route", async () => {
    renderApp({ route: "/status" });

    expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "All systems operational" }),
    ).toBeInTheDocument();
  });

  it("renders not found for unknown routes", () => {
    renderApp({ route: "/missing-route" });

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

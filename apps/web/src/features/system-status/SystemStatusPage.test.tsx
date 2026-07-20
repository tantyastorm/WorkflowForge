import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ApiError } from "../../lib/api-client";
import { renderWithProviders } from "../../test/render";
import { getApiLiveness, getApiReadiness, getDependencyHealth } from "./api";
import { SystemStatusPage } from "./SystemStatusPage";
import type { DependencyHealth } from "./types";

vi.mock("./api", () => ({
  getApiLiveness: vi.fn(),
  getApiReadiness: vi.fn(),
  getDependencyHealth: vi.fn(),
}));

const getApiLivenessMock = vi.mocked(getApiLiveness);
const getApiReadinessMock = vi.mocked(getApiReadiness);
const getDependencyHealthMock = vi.mocked(getDependencyHealth);

const healthyDependencyHealth: DependencyHealth = {
  status: "healthy",
  checked_at: "2026-07-20T10:30:00Z",
  dependencies: {
    postgresql: { status: "healthy", latency_ms: 4.2, detail: null },
    redis: { status: "healthy", latency_ms: 2, detail: null },
    object_storage: { status: "healthy", latency_ms: 12.5, detail: null },
    worker: { status: "healthy", latency_ms: 25, detail: "1 worker responded." },
    scheduler: { status: "healthy", latency_ms: 3.8, detail: null },
  },
};

describe("SystemStatusPage", () => {
  beforeEach(() => {
    getApiLivenessMock.mockResolvedValue({ status: "ok", service: "api" });
    getApiReadinessMock.mockResolvedValue({ status: "ready", service: "api" });
    getDependencyHealthMock.mockResolvedValue(healthyDependencyHealth);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders an accessible loading state", () => {
    getApiLivenessMock.mockReturnValue(new Promise(() => undefined));
    getApiReadinessMock.mockReturnValue(new Promise(() => undefined));
    getDependencyHealthMock.mockReturnValue(new Promise(() => undefined));

    renderWithProviders(<SystemStatusPage />);

    expect(screen.getByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking platform status");
  });

  it("renders all healthy status data", async () => {
    renderWithProviders(<SystemStatusPage />);

    expect(
      await screen.findByRole("heading", { name: "All systems operational" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("API liveness").length).toBeGreaterThan(0);
    expect(screen.getAllByText("API readiness").length).toBeGreaterThan(0);
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("Object storage")).toBeInTheDocument();
    expect(screen.getByText("Worker")).toBeInTheDocument();
    expect(screen.getByText("Scheduler")).toBeInTheDocument();
    expect(screen.queryByText("object_storage")).not.toBeInTheDocument();
    expect(screen.getByText("4.2 ms")).toBeInTheDocument();
    expect(screen.getByText(/Jul 20, 2026|20 Jul 2026|20 July 2026/)).toBeInTheDocument();
  });

  it("renders one unhealthy dependency as degraded", async () => {
    getDependencyHealthMock.mockResolvedValue({
      ...healthyDependencyHealth,
      status: "unhealthy",
      dependencies: {
        ...healthyDependencyHealth.dependencies,
        worker: { status: "unhealthy", latency_ms: 3000, detail: "No workers responded." },
      },
    });

    renderWithProviders(<SystemStatusPage />);

    expect(await screen.findByRole("heading", { name: "Platform degraded" })).toBeInTheDocument();
    const workerCard = screen.getByRole("article", { name: /worker/i });
    expect(within(workerCard).getByText("Unhealthy")).toBeInTheDocument();
    expect(within(workerCard).getByText("No workers responded.")).toBeInTheDocument();
  });

  it("renders API unavailable when liveness fails", async () => {
    getApiLivenessMock.mockRejectedValue(
      new ApiError({
        status: null,
        code: "NETWORK_ERROR",
        message: "Request failed.",
        correlationId: "live-123",
      }),
    );

    renderWithProviders(<SystemStatusPage />);

    expect(await screen.findAllByRole("heading", { name: "API unavailable" })).toHaveLength(2);
    expect(screen.getAllByText(/Correlation ID: live-123/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("keeps liveness visible when readiness fails", async () => {
    getApiReadinessMock.mockRejectedValue(
      new ApiError({ status: 500, code: "HTTP_ERROR", message: "Request failed." }),
    );

    renderWithProviders(<SystemStatusPage />);

    await waitFor(() => {
      expect(getApiReadinessMock).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findAllByText("API process responds")).toHaveLength(2);
    expect(await screen.findAllByText("Request failed.")).not.toHaveLength(0);
  });

  it("renders dependency 503 data as degraded status", async () => {
    getDependencyHealthMock.mockResolvedValue({
      ...healthyDependencyHealth,
      status: "unhealthy",
      dependencies: {
        ...healthyDependencyHealth.dependencies,
        scheduler: { status: "unhealthy", latency_ms: 90, detail: "Heartbeat missing." },
      },
    });

    renderWithProviders(<SystemStatusPage />);

    expect(await screen.findByRole("heading", { name: "Platform degraded" })).toBeInTheDocument();
    const schedulerCard = screen.getByRole("article", { name: /scheduler/i });
    expect(within(schedulerCard).getByText("Unhealthy")).toBeInTheDocument();
    expect(within(schedulerCard).getByText("Heartbeat missing.")).toBeInTheDocument();
  });

  it("renders malformed dependency payloads as unknown", async () => {
    getDependencyHealthMock.mockRejectedValue(
      new ApiError({ status: null, code: "INVALID_RESPONSE", message: "Malformed" }),
    );

    renderWithProviders(<SystemStatusPage />);

    expect(await screen.findByRole("heading", { name: "Status unknown" })).toBeInTheDocument();
    expect(await screen.findByText(/Dependency status is unknown/i)).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  });

  it("refreshes all health queries manually", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SystemStatusPage />);

    await screen.findByRole("heading", { name: "All systems operational" });
    await user.click(screen.getByRole("button", { name: "Refresh status" }));

    await waitFor(() => {
      expect(getApiLivenessMock).toHaveBeenCalledTimes(2);
      expect(getApiReadinessMock).toHaveBeenCalledTimes(2);
      expect(getDependencyHealthMock).toHaveBeenCalledTimes(2);
    });
  });
});

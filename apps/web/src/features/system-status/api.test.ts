import { ApiClient } from "../../lib/api-client";
import { getApiLiveness, getApiReadiness, getDependencyHealth } from "./api";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", headers.get("Content-Type") ?? "application/json");
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers,
  });
}

const healthyDependencies = {
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

describe("system status API", () => {
  it("parses a valid liveness response", async () => {
    const client = clientFor({ status: "ok", service: "api" });

    await expect(getApiLiveness(client)).resolves.toEqual({ status: "ok", service: "api" });
  });

  it("parses a valid readiness response", async () => {
    const client = clientFor({ status: "ready", service: "api" });

    await expect(getApiReadiness(client)).resolves.toEqual({ status: "ready", service: "api" });
  });

  it("parses a valid healthy dependency response", async () => {
    const client = clientFor(healthyDependencies);

    await expect(getDependencyHealth(client)).resolves.toEqual(healthyDependencies);
  });

  it("parses an unhealthy dependency response returned with 503", async () => {
    const unhealthyDependencies = {
      ...healthyDependencies,
      status: "unhealthy",
      dependencies: {
        ...healthyDependencies.dependencies,
        worker: { status: "unhealthy", latency_ms: 3000, detail: "No workers responded." },
      },
    };
    const client = clientFor(unhealthyDependencies, { status: 503 });

    await expect(getDependencyHealth(client)).resolves.toEqual(unhealthyDependencies);
  });

  it("rejects malformed responses", async () => {
    const client = clientFor({ status: "ok" });

    await expect(getApiLiveness(client)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      message: "Health response was malformed.",
    });
  });

  it("preserves correlation IDs on genuine API errors", async () => {
    const client = clientFor(
      { detail: "sanitized" },
      {
        status: 500,
        statusText: "Internal Server Error",
        headers: { "X-Correlation-ID": "request-123" },
      },
    );

    await expect(getDependencyHealth(client)).rejects.toMatchObject({
      status: 500,
      code: "HTTP_ERROR",
      correlationId: "request-123",
    });
  });
});

function clientFor(body: unknown, init: ResponseInit = {}) {
  return new ApiClient({
    baseUrl: "http://localhost:8000",
    fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(body, init)),
  });
}

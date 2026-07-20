import { ApiClient, ApiError, joinUrl } from "./api-client";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", headers.get("Content-Type") ?? "application/json");
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers,
  });
}

describe("ApiClient", () => {
  it("returns successful JSON responses with correlation ID", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        { status: "ok" },
        {
          headers: {
            "Content-Type": "application/json",
            "X-Correlation-ID": "correlation-id",
          },
        },
      ),
    );
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: fetchMock,
    });

    const result = await client.request<{ status: string }>("/health/live", {
      correlationId: "request-id",
    });

    expect(result).toEqual({
      data: { status: "ok" },
      status: 200,
      correlationId: "correlation-id",
    });
    const [, requestInit] = fetchMock.mock.calls[0] ?? [];
    expect(requestInit?.headers).toBeInstanceOf(Headers);
    expect((requestInit?.headers as Headers).get("Accept")).toBe("application/json");
    expect((requestInit?.headers as Headers).get("X-Correlation-ID")).toBe("request-id");
  });

  it("handles non-JSON success responses safely", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("plain text", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      }),
    );
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    const result = await client.request<null>("/empty");

    expect(result.data).toBeNull();
    expect(result.status).toBe(200);
  });

  it("throws typed HTTP errors without leaking response body", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        { detail: "secret backend detail" },
        {
          status: 503,
          statusText: "Service Unavailable",
          headers: { "X-Correlation-ID": "response-id" },
        },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    await expect(client.request("/health/dependencies")).rejects.toMatchObject({
      status: 503,
      code: "HTTP_ERROR",
      message: "Service Unavailable",
      correlationId: "response-id",
      timeout: false,
    });
    await expect(client.request("/health/dependencies")).rejects.not.toThrow(
      /secret backend detail/i,
    );
  });

  it("distinguishes timeout failures", async () => {
    const fetchMock = vi.fn<typeof fetch>(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: fetchMock,
      timeoutMs: 1,
    });

    await expect(client.request("/slow")).rejects.toMatchObject({
      code: "TIMEOUT",
      status: null,
      timeout: true,
    });
  });

  it("sends JSON content type only when a body is present", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ ok: true }));
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    await client.request("/items");
    await client.request("/items", { method: "POST", body: { name: "demo" } });

    const firstHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    const secondHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Headers;
    expect(firstHeaders.get("Content-Type")).toBeNull();
    expect(secondHeaders.get("Content-Type")).toBe("application/json");
  });

  it("joins URLs without duplicate slashes", () => {
    expect(joinUrl("http://localhost:8000///", "///health/live")).toBe(
      "http://localhost:8000/health/live",
    );
  });

  it("creates typed errors", () => {
    const error = new ApiError({
      status: 500,
      code: "HTTP_ERROR",
      message: "Request failed.",
    });

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
  });
});

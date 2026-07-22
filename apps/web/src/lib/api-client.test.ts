import { ApiClient, ApiError, joinUrl, readCookie } from "./api-client";

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
        { error: { code: "rate_limited", message: "Too many attempts." } },
        {
          status: 429,
          statusText: "Too Many Requests",
          headers: { "X-Correlation-ID": "response-id", "Retry-After": "42" },
        },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    await expect(client.request("/health/dependencies")).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
      message: "Too many attempts.",
      correlationId: "response-id",
      timeout: false,
      retryAfterSeconds: 42,
    });
    await expect(client.request("/health/dependencies")).rejects.not.toThrow(
      /secret backend detail|refresh token/i,
    );
  });

  it("accepts explicitly expected non-2xx responses", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        { status: "unhealthy" },
        {
          status: 503,
          statusText: "Service Unavailable",
          headers: { "X-Correlation-ID": "response-id" },
        },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    const result = await client.request<{ status: string }>("/health/dependencies", {
      expectedStatuses: [200, 503],
    });

    expect(result).toEqual({
      data: { status: "unhealthy" },
      status: 503,
      correlationId: "response-id",
    });
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

  it("sends bearer and CSRF headers without exposing refresh tokens", async () => {
    document.cookie = "csrf_cookie=csrf-value; path=/";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ ok: true }));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      csrfCookieName: "csrf_cookie",
      csrfHeaderName: "X-CSRF-Test",
      fetchImpl: fetchMock,
    });
    client.setAccessTokenProvider(() => "access-token");

    await client.request("/api/v1/auth/logout", {
      method: "POST",
      authenticated: true,
      credentials: "include",
      csrf: true,
    });

    const requestInit = fetchMock.mock.calls[0]?.[1];
    const headers = requestInit?.headers as Headers;
    expect(requestInit?.credentials).toBe("include");
    expect(headers.get("Authorization")).toBe("Bearer access-token");
    expect(headers.get("X-CSRF-Test")).toBe("csrf-value");
    expect(headers.get("Cookie")).toBeNull();
  });

  it("retries authenticated 401 responses once after refresh", async () => {
    let token = "old-access";
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "authentication_failed", message: "Authentication is required." } },
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    const refreshHandler = vi.fn(() => {
      token = "new-access";
      return Promise.resolve(token);
    });
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });
    client.setAccessTokenProvider(() => token);
    client.setRefreshHandler(refreshHandler);

    const result = await client.request<{ ok: boolean }>("/api/v1/auth/me", {
      authenticated: true,
    });

    expect(result.data).toEqual({ ok: true });
    expect(refreshHandler).toHaveBeenCalledTimes(1);
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer old-access",
    );
    expect((fetchMock.mock.calls[1]?.[1]?.headers as Headers).get("Authorization")).toBe(
      "Bearer new-access",
    );
  });

  it("does not refresh 403 or 429 responses", async () => {
    const refreshHandler = vi.fn(() => Promise.resolve("new-access"));
    const forbiddenClient = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "permission_denied", message: "The request is not allowed." } },
            { status: 403 },
          ),
        ),
    });
    forbiddenClient.setAccessTokenProvider(() => "access-token");
    forbiddenClient.setRefreshHandler(refreshHandler);

    await expect(
      forbiddenClient.request("/api/v1/secure", { authenticated: true }),
    ).rejects.toMatchObject({
      status: 403,
      code: "permission_denied",
    });
    expect(refreshHandler).not.toHaveBeenCalled();

    const rateLimitedClient = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "rate_limited", message: "Too many attempts." } },
            { status: 429 },
          ),
        ),
    });
    rateLimitedClient.setAccessTokenProvider(() => "access-token");
    rateLimitedClient.setRefreshHandler(refreshHandler);

    await expect(
      rateLimitedClient.request("/api/v1/secure", { authenticated: true }),
    ).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
    });
    expect(refreshHandler).not.toHaveBeenCalled();
  });

  it("does not recursively refresh refresh endpoint failures", async () => {
    const refreshHandler = vi.fn(() => Promise.resolve("new-access"));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      csrfCookieName: "csrf_cookie",
      csrfHeaderName: "X-CSRF-Test",
      fetchImpl: vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: "authentication_failed", message: "Authentication failed." } },
            { status: 401 },
          ),
        ),
    });
    client.setRefreshHandler(refreshHandler);

    await expect(
      client.request("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "include",
        csrf: true,
        retryOnUnauthorized: false,
      }),
    ).rejects.toMatchObject({ status: 401 });
    expect(refreshHandler).not.toHaveBeenCalled();
  });

  it("rejects absolute and protocol-relative request paths", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ ok: true }));
    const client = new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchMock });

    await expect(client.request("https://evil.example/api")).rejects.toMatchObject({
      code: "INVALID_REQUEST_PATH",
    });
    await expect(client.request("//evil.example/api")).rejects.toMatchObject({
      code: "INVALID_REQUEST_PATH",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("parses Retry-After HTTP dates", async () => {
    vi.spyOn(Date, "now").mockReturnValue(new Date("2026-01-02T03:04:05Z").getTime());
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      csrfCookieName: "csrf_cookie",
      csrfHeaderName: "X-CSRF-Test",
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          { error: { code: "rate_limited", message: "Too many attempts." } },
          {
            status: 429,
            headers: { "Retry-After": "Fri, 02 Jan 2026 03:04:15 GMT" },
          },
        ),
      ),
    });

    await expect(client.request("/api/v1/auth/login")).rejects.toMatchObject({
      retryAfterSeconds: 10,
    });
  });

  it("joins URLs without duplicate slashes", () => {
    expect(joinUrl("http://localhost:8000///", "/health/live")).toBe(
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

  it("reads exact, encoded, and safe CSRF cookie values", () => {
    document.cookie = "workflowforge_csrf=token; path=/";
    document.cookie = "workflowforge_csrf_extra=wrong; path=/";

    expect(readCookie("workflowforge_csrf")).toBe("token");

    document.cookie = "encoded_csrf=value%2Bwith%2Fsymbols; path=/";
    expect(readCookie("encoded_csrf")).toBe("value+with/symbols");

    document.cookie = "empty_csrf=; path=/";
    expect(readCookie("empty_csrf")).toBeNull();

    document.cookie = "bad_csrf=%E0%A4%A; path=/";
    expect(readCookie("bad_csrf")).toBeNull();

    expect(readCookie("missing_csrf")).toBeNull();
  });
});

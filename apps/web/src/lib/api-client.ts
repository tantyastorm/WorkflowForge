import { getEnvironment } from "./env";

const CORRELATION_ID_HEADER = "X-Correlation-ID";
const DEFAULT_TIMEOUT_MS = 10_000;

export type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
};

export type ApiRequestOptions = {
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
  correlationId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type ApiSuccess<T> = {
  data: T;
  status: number;
  correlationId: string | null;
};

export class ApiError extends Error {
  public readonly status: number | null;
  public readonly code: string;
  public readonly correlationId: string | null;
  public readonly timeout: boolean;

  public constructor(params: {
    message: string;
    status: number | null;
    code: string;
    correlationId?: string | null;
    timeout?: boolean;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.correlationId = params.correlationId ?? null;
    this.timeout = params.timeout ?? false;
  }
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  public constructor(options: ApiClientOptions = {}) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl ?? getEnvironment().apiBaseUrl);
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  public async request<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiSuccess<T>> {
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    const timeoutController = new AbortController();
    const timeoutId = window.setTimeout(() => {
      timeoutController.abort();
    }, timeoutMs);

    const signal = mergeAbortSignals(timeoutController, options.signal);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");

    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    }

    if (options.correlationId !== undefined) {
      headers.set(CORRELATION_ID_HEADER, options.correlationId);
    }

    try {
      const requestInit: RequestInit = {
        method: options.method ?? "GET",
        headers,
        signal,
      };
      if (body !== undefined) {
        requestInit.body = body;
      }

      const response = await this.fetchImpl(joinUrl(this.baseUrl, path), requestInit);
      const correlationId = response.headers.get(CORRELATION_ID_HEADER);
      const data = await parseResponseBody(response);

      if (!response.ok) {
        throw new ApiError({
          status: response.status,
          code: "HTTP_ERROR",
          message: response.statusText || "Request failed.",
          correlationId,
        });
      }

      return {
        data: data as T,
        status: response.status,
        correlationId,
      };
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError({
          status: null,
          code: "TIMEOUT",
          message: "Request timed out.",
          timeout: true,
        });
      }
      throw new ApiError({
        status: null,
        code: "NETWORK_ERROR",
        message: "Request failed.",
      });
    } finally {
      window.clearTimeout(timeoutId);
    }
  }
}

export function createApiClient(options?: ApiClientOptions) {
  return new ApiClient(options);
}

export function joinUrl(baseUrl: string, path: string): string {
  const normalizedBase = normalizeBaseUrl(baseUrl);
  const normalizedPath = path.replace(/^\/+/, "");
  return `${normalizedBase}/${normalizedPath}`;
}

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function mergeAbortSignals(primary: AbortController, secondary?: AbortSignal): AbortSignal {
  if (secondary === undefined) {
    return primary.signal;
  }
  if (secondary.aborted) {
    primary.abort();
    return primary.signal;
  }
  secondary.addEventListener(
    "abort",
    () => {
      primary.abort();
    },
    { once: true },
  );
  return primary.signal;
}

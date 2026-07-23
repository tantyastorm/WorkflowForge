import { getEnvironment } from "./env";

const CORRELATION_ID_HEADER = "X-Correlation-ID";
const DEFAULT_TIMEOUT_MS = 10_000;
const RETRY_AFTER_HEADER = "Retry-After";

export type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  csrfCookieName?: string;
  csrfHeaderName?: string;
};

export type ApiRequestOptions = {
  method?: string;
  body?: unknown;
  rawBody?: BodyInit;
  headers?: HeadersInit;
  correlationId?: string;
  expectedStatuses?: readonly number[];
  signal?: AbortSignal;
  timeoutMs?: number;
  authenticated?: boolean;
  credentials?: RequestCredentials;
  csrf?: boolean;
  retryOnUnauthorized?: boolean;
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
  public readonly retryAfterSeconds: number | null;

  public constructor(params: {
    message: string;
    status: number | null;
    code: string;
    correlationId?: string | null;
    timeout?: boolean;
    retryAfterSeconds?: number | null;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.correlationId = params.correlationId ?? null;
    this.timeout = params.timeout ?? false;
    this.retryAfterSeconds = params.retryAfterSeconds ?? null;
  }
}

export class ApiClient {
  private readonly configuredBaseUrl: string | null;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly configuredCsrfCookieName: string | null;
  private readonly configuredCsrfHeaderName: string | null;
  private accessTokenProvider: (() => string | null) | null = null;
  private refreshHandler: (() => Promise<string | null>) | null = null;

  public constructor(options: ApiClientOptions = {}) {
    this.configuredBaseUrl =
      options.baseUrl === undefined ? null : normalizeBaseUrl(options.baseUrl);
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.configuredCsrfCookieName = options.csrfCookieName ?? null;
    this.configuredCsrfHeaderName = options.csrfHeaderName ?? null;
  }

  public setAccessTokenProvider(provider: (() => string | null) | null): void {
    this.accessTokenProvider = provider;
  }

  public setRefreshHandler(handler: (() => Promise<string | null>) | null): void {
    this.refreshHandler = handler;
  }

  public async request<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiSuccess<T>> {
    return await this.requestWithAuthRetry<T>(path, options, false);
  }

  private async requestWithAuthRetry<T>(
    path: string,
    options: ApiRequestOptions,
    retried: boolean,
  ): Promise<ApiSuccess<T>> {
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    const timeoutController = new AbortController();
    const timeoutId = window.setTimeout(() => {
      timeoutController.abort();
    }, timeoutMs);

    const signal = mergeAbortSignals(timeoutController, options.signal);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.authenticated) {
      const accessToken = this.accessTokenProvider?.();
      if (accessToken !== undefined && accessToken !== null && accessToken !== "") {
        headers.set("Authorization", `Bearer ${accessToken}`);
      }
    }
    if (options.csrf) {
      const csrfToken = readCookie(this.csrfCookieName);
      if (csrfToken !== null) {
        headers.set(this.csrfHeaderName, csrfToken);
      }
    }

    let body: BodyInit | undefined;
    if (options.body !== undefined && options.rawBody !== undefined) {
      throw new ApiError({
        status: null,
        code: "INVALID_REQUEST_BODY",
        message: "API requests must use either body or rawBody.",
      });
    }
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    } else if (options.rawBody !== undefined) {
      body = options.rawBody;
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
      if (options.credentials !== undefined) {
        requestInit.credentials = options.credentials;
      }
      if (body !== undefined) {
        requestInit.body = body;
      }

      const response = await this.fetchImpl(joinUrl(this.baseUrl, path), requestInit);
      const correlationId = response.headers.get(CORRELATION_ID_HEADER);
      const data = await parseResponseBody(response);

      if (!isExpectedStatus(response.status, options.expectedStatuses)) {
        if (
          response.status === 401 &&
          options.authenticated === true &&
          options.retryOnUnauthorized !== false &&
          !retried &&
          this.refreshHandler !== null
        ) {
          const refreshedToken = await this.refreshHandler();
          if (refreshedToken !== null) {
            return await this.requestWithAuthRetry<T>(path, options, true);
          }
        }
        throw new ApiError({
          status: response.status,
          code: responseErrorCode(data),
          message: responseErrorMessage(data, response.statusText),
          correlationId,
          retryAfterSeconds: parseRetryAfter(response.headers.get(RETRY_AFTER_HEADER)),
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

  private get baseUrl(): string {
    return this.configuredBaseUrl ?? getEnvironment().apiBaseUrl;
  }

  private get csrfCookieName(): string {
    return this.configuredCsrfCookieName ?? getEnvironment().csrfCookieName;
  }

  private get csrfHeaderName(): string {
    return this.configuredCsrfHeaderName ?? getEnvironment().csrfHeaderName;
  }
}

export function createApiClient(options?: ApiClientOptions) {
  return new ApiClient(options);
}

export const apiClient = createApiClient();

export function joinUrl(baseUrl: string, path: string): string {
  if (isAbsoluteOrProtocolRelativePath(path)) {
    throw new ApiError({
      status: null,
      code: "INVALID_REQUEST_PATH",
      message: "API request paths must be relative.",
    });
  }
  const normalizedBase = normalizeBaseUrl(baseUrl);
  const normalizedPath = path.replace(/^\/+/, "");
  return `${normalizedBase}/${normalizedPath}`;
}

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function isExpectedStatus(status: number, expectedStatuses?: readonly number[]): boolean {
  if (expectedStatuses !== undefined) {
    return expectedStatuses.includes(status);
  }
  return status >= 200 && status < 300;
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

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const cookiePrefix = `${encodeURIComponent(name)}=`;
  const cookies = document.cookie.split("; ");
  for (const cookie of cookies) {
    if (cookie.startsWith(cookiePrefix)) {
      const rawValue = cookie.slice(cookiePrefix.length);
      if (rawValue === "") {
        return null;
      }
      try {
        return decodeURIComponent(rawValue);
      } catch {
        return null;
      }
    }
  }
  return null;
}

function responseErrorCode(data: unknown): string {
  if (isErrorResponse(data)) {
    return data.error.code;
  }
  return "HTTP_ERROR";
}

function responseErrorMessage(data: unknown, fallback: string): string {
  if (isErrorResponse(data)) {
    return data.error.message;
  }
  return fallback || "Request failed.";
}

function isErrorResponse(data: unknown): data is { error: { code: string; message: string } } {
  if (typeof data !== "object" || data === null || !("error" in data)) {
    return false;
  }
  const error = data.error;
  if (typeof error !== "object" || error === null) {
    return false;
  }
  const details = error as { code?: unknown; message?: unknown };
  return typeof details.code === "string" && typeof details.message === "string";
}

function parseRetryAfter(value: string | null): number | null {
  if (value === null) {
    return null;
  }
  const seconds = Number.parseInt(value, 10);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds;
  }
  const retryAt = Date.parse(value);
  if (Number.isFinite(retryAt)) {
    return Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000));
  }
  return null;
}

function isAbsoluteOrProtocolRelativePath(path: string): boolean {
  return /^[a-z][a-z\d+\-.]*:/i.test(path) || path.startsWith("//");
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

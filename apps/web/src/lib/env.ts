import { z } from "zod";

const environmentSchema = z.object({
  VITE_API_BASE_URL: z
    .string()
    .min(1, "VITE_API_BASE_URL is required.")
    .pipe(z.url("VITE_API_BASE_URL must be an absolute URL."))
    .refine((value) => {
      const protocol = new URL(value).protocol;
      return protocol === "http:" || protocol === "https:";
    }, "VITE_API_BASE_URL must use HTTP or HTTPS."),
  VITE_CSRF_COOKIE_NAME: z.string().min(1).default("workflowforge_csrf"),
  VITE_CSRF_HEADER_NAME: z.string().min(1).default("X-CSRF-Token"),
});

export type FrontendEnvironment = {
  apiBaseUrl: string;
  csrfCookieName: string;
  csrfHeaderName: string;
};

export function parseEnvironment(source: Record<string, string | undefined>): FrontendEnvironment {
  const parsed = environmentSchema.parse({
    VITE_API_BASE_URL: source.VITE_API_BASE_URL,
    VITE_CSRF_COOKIE_NAME: source.VITE_CSRF_COOKIE_NAME,
    VITE_CSRF_HEADER_NAME: source.VITE_CSRF_HEADER_NAME,
  });

  return {
    apiBaseUrl: normalizeBaseUrl(parsed.VITE_API_BASE_URL),
    csrfCookieName: parsed.VITE_CSRF_COOKIE_NAME,
    csrfHeaderName: parsed.VITE_CSRF_HEADER_NAME,
  };
}

export function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getEnvironment(): FrontendEnvironment {
  return parseEnvironment(import.meta.env);
}

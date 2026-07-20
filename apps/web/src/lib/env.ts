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
});

export type FrontendEnvironment = {
  apiBaseUrl: string;
};

export function parseEnvironment(source: Record<string, string | undefined>): FrontendEnvironment {
  const parsed = environmentSchema.parse({
    VITE_API_BASE_URL: source.VITE_API_BASE_URL,
  });

  return {
    apiBaseUrl: normalizeBaseUrl(parsed.VITE_API_BASE_URL),
  };
}

export function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getEnvironment(): FrontendEnvironment {
  return parseEnvironment(import.meta.env);
}

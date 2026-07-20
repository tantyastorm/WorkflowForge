import { z } from "zod";

export const dependencyNames = [
  "postgresql",
  "redis",
  "object_storage",
  "worker",
  "scheduler",
] as const;

export type DependencyName = (typeof dependencyNames)[number];
export type ApiLivenessStatus = "ok";
export type ApiReadinessStatus = "ready" | "not_ready";
export type DependencyStatus = "healthy" | "unhealthy";
export type AggregateHealthStatus = "healthy" | "unhealthy";

const dependencyHealthItemSchema = z
  .object({
    status: z.enum(["healthy", "unhealthy"]),
    latency_ms: z.number().nonnegative(),
    detail: z.string().nullable().optional(),
  })
  .strict();

export const apiLivenessSchema = z
  .object({
    status: z.literal("ok"),
    service: z.literal("api"),
  })
  .strict();

export const apiReadinessSchema = z
  .object({
    status: z.enum(["ready", "not_ready"]),
    service: z.literal("api"),
  })
  .strict();

export const dependencyHealthSchema = z
  .object({
    status: z.enum(["healthy", "unhealthy"]),
    checked_at: z.string().refine((value) => !Number.isNaN(Date.parse(value)), {
      message: "checked_at must be a valid date-time string.",
    }),
    dependencies: z
      .object({
        postgresql: dependencyHealthItemSchema,
        redis: dependencyHealthItemSchema,
        object_storage: dependencyHealthItemSchema,
        worker: dependencyHealthItemSchema,
        scheduler: dependencyHealthItemSchema,
      })
      .strict(),
  })
  .strict();

export type ApiLiveness = z.infer<typeof apiLivenessSchema>;
export type ApiReadiness = z.infer<typeof apiReadinessSchema>;
export type DependencyHealthItem = z.infer<typeof dependencyHealthItemSchema>;
export type DependencyHealth = z.infer<typeof dependencyHealthSchema>;

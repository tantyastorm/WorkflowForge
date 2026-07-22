import { z } from "zod";

export const tokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("Bearer"),
  access_token_expires_at: z.string().min(1),
  session_id: z.uuid(),
});

export const meResponseSchema = z.object({
  user_id: z.uuid(),
  session_id: z.uuid(),
  issued_at: z.string().min(1),
  expires_at: z.string().min(1),
});

export const userOrganizationSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
  slug: z.string().min(1),
  membership_id: z.uuid(),
  membership_role: z.enum(["owner", "admin", "operator", "reviewer", "auditor"]),
  membership_status: z.enum(["active", "invited", "suspended", "removed"]),
});

export const permissionSchema = z.enum([
  "organization.read",
  "organization.update",
  "membership.read",
  "membership.invite",
  "membership.update",
  "membership.remove",
  "audit.read",
  "security.manage",
  "api_keys.manage",
  "provider_credentials.manage",
]);

export const tenantContextSchema = z.object({
  user_id: z.uuid(),
  organization_id: z.uuid(),
  membership_id: z.uuid(),
  role: userOrganizationSchema.shape.membership_role,
  permissions: z.array(permissionSchema),
});

export const logoutResponseSchema = z.object({
  revoked: z.boolean(),
});

export const logoutAllResponseSchema = z.object({
  revoked_sessions: z.number().int().nonnegative(),
});

export type TokenResponse = z.infer<typeof tokenResponseSchema>;
export type MeResponse = z.infer<typeof meResponseSchema>;
export type UserOrganization = z.infer<typeof userOrganizationSchema>;
export type Permission = z.infer<typeof permissionSchema>;
export type TenantContext = z.infer<typeof tenantContextSchema>;

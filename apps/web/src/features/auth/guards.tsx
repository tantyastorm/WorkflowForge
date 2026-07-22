import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { LoadingState } from "../../components/feedback/LoadingState";
import type { Permission } from "./types";
import { useAuth } from "./auth-context";

export function RequireAuthentication({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "initializing") {
    return <LoadingState message="Restoring session" />;
  }
  if (auth.status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}

export function RequireOrganization({ children }: { children: ReactNode }) {
  const auth = useAuth();
  if (auth.organizations.length === 0 || auth.selectedOrganizationId === null) {
    return <Navigate to="/select-organization" replace />;
  }
  return <>{children}</>;
}

export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const auth = useAuth();
  if (!auth.hasPermission(permission)) {
    return <Navigate to="/forbidden" replace />;
  }
  return <>{children}</>;
}

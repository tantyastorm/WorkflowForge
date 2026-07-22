import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { ErrorState } from "../components/feedback/ErrorState";
import { AppShell } from "../components/layout/AppShell";
import { ForbiddenPage } from "../features/auth/ForbiddenPage";
import {
  RequireAuthentication,
  RequireOrganization,
  RequirePermission,
} from "../features/auth/guards";
import { LoginPage } from "../features/auth/LoginPage";
import { OrganizationSelectionPage } from "../features/auth/OrganizationSelectionPage";
import { TenantContextPage } from "../features/auth/TenantContextPage";
import { HomePage } from "../features/home/HomePage";
import { SystemStatusPage } from "../features/system-status/SystemStatusPage";

export const appRoutes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      {
        path: "/",
        element: <HomePage />,
      },
      {
        path: "/status",
        element: <SystemStatusPage />,
      },
      {
        path: "/login",
        element: <LoginPage />,
      },
      {
        path: "/select-organization",
        element: <OrganizationSelectionPage />,
      },
      {
        path: "/forbidden",
        element: <ForbiddenPage />,
      },
      {
        path: "/app",
        element: (
          <RequireAuthentication>
            <RequireOrganization>
              <Navigate to="/app/system" replace />
            </RequireOrganization>
          </RequireAuthentication>
        ),
      },
      {
        path: "/app/system",
        element: (
          <RequireAuthentication>
            <RequireOrganization>
              <SystemStatusPage />
            </RequireOrganization>
          </RequireAuthentication>
        ),
      },
      {
        path: "/app/tenant-context",
        element: (
          <RequireAuthentication>
            <RequireOrganization>
              <RequirePermission permission="organization.read">
                <TenantContextPage />
              </RequirePermission>
            </RequireOrganization>
          </RequireAuthentication>
        ),
      },
      {
        path: "*",
        element: (
          <ErrorState
            title="Page not found"
            message="This route is not part of the WorkflowForge foundation yet."
          />
        ),
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(appRoutes);
}

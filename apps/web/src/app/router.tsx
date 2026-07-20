import { createBrowserRouter, type RouteObject } from "react-router";

import { ErrorState } from "../components/feedback/ErrorState";
import { AppShell } from "../components/layout/AppShell";
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

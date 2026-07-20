import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { AppErrorBoundary } from "../app/error-boundary";
import { appRoutes } from "../app/router";
import { createQueryClient } from "../lib/query-client";

type RenderAppOptions = RenderOptions & {
  route?: string;
};

export function renderApp({ route = "/", ...options }: RenderAppOptions = {}) {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(appRoutes, { initialEntries: [route] });

  return render(
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </AppErrorBoundary>,
    options,
  );
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  const queryClient = createQueryClient();

  return render(
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </AppErrorBoundary>,
    options,
  );
}

import { QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { AppErrorBoundary } from "./error-boundary";
import { createQueryClient } from "../lib/query-client";

const queryClient = createQueryClient();

export function AppProviders() {
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}

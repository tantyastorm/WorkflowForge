import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "../components/feedback/ErrorState";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
};

export class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public override state: ErrorBoundaryState = {
    hasError: false,
  };

  public static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  public override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("Render error captured by boundary.", {
      message: error instanceof Error ? error.message : "Unknown render error.",
      componentStack: info.componentStack,
    });
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <ErrorState
          title="Something went wrong"
          message="The interface could not render this view. Try again to reset the page state."
          actionLabel="Try again"
          onRetry={() => {
            this.setState({ hasError: false });
          }}
        />
      );
    }

    return this.props.children;
  }
}

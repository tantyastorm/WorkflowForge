import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppErrorBoundary } from "./error-boundary";
import { renderWithProviders } from "../test/render";

function BrokenView(): never {
  throw new Error("secret stack detail");
}

let shouldThrow = true;

function RecoverableView() {
  if (shouldThrow) {
    throw new Error("temporary render failure");
  }
  return <p>Recovered view</p>;
}

describe("AppErrorBoundary", () => {
  it("renders a sanitized fallback for render errors", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    renderWithProviders(
      <AppErrorBoundary>
        <BrokenView />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.queryByText(/secret stack detail/i)).not.toBeInTheDocument();
  });

  it("supports reset through the retry action", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const user = userEvent.setup();

    renderWithProviders(
      <AppErrorBoundary>
        <RecoverableView />
      </AppErrorBoundary>,
    );

    shouldThrow = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.getByText("Recovered view")).toBeInTheDocument();
    shouldThrow = true;
  });
});

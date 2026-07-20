import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { renderWithProviders } from "../../test/render";

describe("feedback components", () => {
  it("renders accessible loading text", () => {
    renderWithProviders(<LoadingState message="Loading foundations" />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading foundations");
  });

  it("renders recoverable error text and retry action", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <ErrorState
        title="Unable to load"
        message="Try the request again."
        actionLabel="Retry"
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("heading", { name: "Unable to load" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

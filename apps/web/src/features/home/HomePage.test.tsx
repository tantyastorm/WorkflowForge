import { screen } from "@testing-library/react";

import { renderApp } from "../../test/render";

describe("HomePage", () => {
  it("renders the root page heading", () => {
    renderApp({ route: "/" });

    expect(screen.getByRole("heading", { level: 1, name: "WorkflowForge" })).toBeInTheDocument();
    expect(
      screen.getByText(/repository foundation is under active development/i),
    ).toBeInTheDocument();
  });

  it("renders the application shell once", () => {
    renderApp({ route: "/" });

    expect(screen.getAllByTestId("app-shell")).toHaveLength(1);
    expect(screen.getByRole("navigation", { name: /primary navigation/i })).toBeInTheDocument();
  });
});

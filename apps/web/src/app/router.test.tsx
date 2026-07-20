import { screen } from "@testing-library/react";

import { renderApp } from "../test/render";

describe("router", () => {
  it("renders the home route", () => {
    renderApp({ route: "/" });

    expect(screen.getByRole("heading", { name: "WorkflowForge" })).toBeInTheDocument();
  });

  it("renders not found for unknown routes", () => {
    renderApp({ route: "/missing-route" });

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

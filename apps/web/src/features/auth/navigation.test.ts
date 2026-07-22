import { destinationFromState } from "./navigation";

describe("destinationFromState", () => {
  it("allows same-origin internal paths", () => {
    expect(destinationFromState({ from: { pathname: "/app/system" } })).toBe("/app/system");
  });

  it("rejects external, protocol-relative, and login return targets", () => {
    expect(destinationFromState({ from: { pathname: "https://evil.example" } })).toBe("/app");
    expect(destinationFromState({ from: { pathname: "//evil.example" } })).toBe("/app");
    expect(destinationFromState({ from: { pathname: "/login" } })).toBe("/app");
    expect(destinationFromState({})).toBe("/app");
  });
});

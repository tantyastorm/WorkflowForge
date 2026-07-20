import { parseEnvironment } from "./env";

describe("parseEnvironment", () => {
  it("parses a valid API base URL", () => {
    expect(parseEnvironment({ VITE_API_BASE_URL: "http://localhost:8000" })).toEqual({
      apiBaseUrl: "http://localhost:8000",
    });
  });

  it("normalizes trailing slashes", () => {
    expect(parseEnvironment({ VITE_API_BASE_URL: "https://api.example.test///" })).toEqual({
      apiBaseUrl: "https://api.example.test",
    });
  });

  it("rejects invalid URLs", () => {
    expect(() => parseEnvironment({ VITE_API_BASE_URL: "localhost:8000" })).toThrow(
      /HTTP or HTTPS/i,
    );
  });

  it("rejects missing values", () => {
    expect(() => parseEnvironment({})).toThrow(/VITE_API_BASE_URL/i);
  });

  it("rejects non-http protocols", () => {
    expect(() => parseEnvironment({ VITE_API_BASE_URL: "ftp://example.test" })).toThrow(
      /HTTP or HTTPS/i,
    );
  });
});

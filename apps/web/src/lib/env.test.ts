import { parseEnvironment } from "./env";

describe("parseEnvironment", () => {
  it("parses a valid API base URL", () => {
    expect(parseEnvironment({ VITE_API_BASE_URL: "http://localhost:8000" })).toEqual({
      apiBaseUrl: "http://localhost:8000",
      csrfCookieName: "workflowforge_csrf",
      csrfHeaderName: "X-CSRF-Token",
    });
  });

  it("normalizes trailing slashes", () => {
    expect(parseEnvironment({ VITE_API_BASE_URL: "https://api.example.test///" })).toEqual({
      apiBaseUrl: "https://api.example.test",
      csrfCookieName: "workflowforge_csrf",
      csrfHeaderName: "X-CSRF-Token",
    });
  });

  it("parses CSRF names", () => {
    expect(
      parseEnvironment({
        VITE_API_BASE_URL: "https://api.example.test",
        VITE_CSRF_COOKIE_NAME: "csrf_cookie",
        VITE_CSRF_HEADER_NAME: "X-Test-CSRF",
      }),
    ).toEqual({
      apiBaseUrl: "https://api.example.test",
      csrfCookieName: "csrf_cookie",
      csrfHeaderName: "X-Test-CSRF",
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

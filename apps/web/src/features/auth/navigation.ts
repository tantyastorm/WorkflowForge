export function destinationFromState(state: unknown): string {
  if (typeof state !== "object" || state === null || !("from" in state)) {
    return "/app";
  }
  const from = state.from;
  if (typeof from !== "object" || from === null || !("pathname" in from)) {
    return "/app";
  }
  if (typeof from.pathname !== "string") {
    return "/app";
  }
  if (!from.pathname.startsWith("/") || from.pathname.startsWith("//")) {
    return "/app";
  }
  if (from.pathname === "/login") {
    return "/app";
  }
  return from.pathname;
}

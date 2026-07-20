import { NavLink, Outlet } from "react-router";

export function AppShell() {
  return (
    <div className="app-shell" data-testid="app-shell">
      <header className="app-shell__header">
        <a className="app-shell__brand" href="/">
          WorkflowForge
        </a>
        <nav className="app-shell__nav" aria-label="Primary navigation">
          <NavLink to="/" className="app-shell__nav-link">
            Home
          </NavLink>
          <NavLink to="/status" className="app-shell__nav-link">
            Status
          </NavLink>
        </nav>
      </header>
      <main className="app-shell__main">
        <Outlet />
      </main>
    </div>
  );
}

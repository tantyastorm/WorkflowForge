import { NavLink, Outlet } from "react-router";

import { useAuth } from "../../features/auth/auth-context";

export function AppShell() {
  const auth = useAuth();
  const selectedOrganization = auth.organizations.find(
    (organization) => organization.id === auth.selectedOrganizationId,
  );

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
          {auth.status === "authenticated" ? (
            <>
              <NavLink to="/app/system" className="app-shell__nav-link">
                System
              </NavLink>
              {auth.hasPermission("document.read") ? (
                <NavLink to="/app/documents" className="app-shell__nav-link">
                  Documents
                </NavLink>
              ) : null}
              {auth.hasPermission("batch.read") ? (
                <NavLink to="/app/batches" className="app-shell__nav-link">
                  Batches
                </NavLink>
              ) : null}
              {auth.hasPermission("case.read") ? (
                <NavLink to="/app/cases" className="app-shell__nav-link">
                  Cases
                </NavLink>
              ) : null}
              {auth.hasPermission("organization.read") ? (
                <NavLink to="/app/tenant-context" className="app-shell__nav-link">
                  Tenant context
                </NavLink>
              ) : null}
            </>
          ) : null}
        </nav>
        <div className="app-shell__session">
          {auth.status === "authenticated" ? (
            <>
              <div className="app-shell__identity">
                <strong>{selectedOrganization?.name ?? "No organization"}</strong>
                <span>{auth.user?.user_id}</span>
              </div>
              {auth.organizations.length > 1 ? (
                <NavLink to="/select-organization" className="button button--secondary">
                  Switch
                </NavLink>
              ) : null}
              <button
                className="button button--secondary"
                type="button"
                onClick={() => void auth.logout()}
              >
                Sign out
              </button>
              <button
                className="button button--danger"
                type="button"
                onClick={() => {
                  if (window.confirm("Sign out of all WorkflowForge sessions?")) {
                    void auth.logoutAll();
                  }
                }}
              >
                Sign out all
              </button>
            </>
          ) : (
            <NavLink to="/login" className="button button--secondary">
              Sign in
            </NavLink>
          )}
        </div>
      </header>
      <main className="app-shell__main">
        <Outlet />
      </main>
    </div>
  );
}

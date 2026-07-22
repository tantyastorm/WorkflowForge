import { useState } from "react";
import { Navigate, useNavigate } from "react-router";

import { ErrorState } from "../../components/feedback/ErrorState";
import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "./auth-context";

export function OrganizationSelectionPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [pendingId, setPendingId] = useState<string | null>(null);

  if (auth.status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }

  async function handleSelect(organizationId: string) {
    setPendingId(organizationId);
    try {
      await auth.selectOrganization(organizationId);
      void navigate("/app", { replace: true });
    } finally {
      setPendingId(null);
    }
  }

  if (auth.organizations.length === 0) {
    return (
      <PageContainer>
        <ErrorState
          title="No organizations available"
          message="Your account has no active organization memberships."
          actionLabel="Sign out"
          onRetry={() => {
            void auth.logout();
          }}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="org-selection">
        <header className="org-selection__header">
          <p className="auth-eyebrow">Organization context</p>
          <h1>Select organization</h1>
        </header>
        {auth.error !== null ? (
          <div className="auth-alert" role="alert">
            <strong>{auth.error.title}</strong>
            <span>{auth.error.message}</span>
          </div>
        ) : null}
        <div className="org-list">
          {auth.organizations.map((organization) => (
            <article className="org-card" key={organization.id}>
              <div>
                <h2>{organization.name}</h2>
                <p>{organization.slug}</p>
              </div>
              <dl>
                <div>
                  <dt>Role</dt>
                  <dd>{organization.membership_role}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{organization.membership_status}</dd>
                </div>
              </dl>
              <button
                className="button"
                type="button"
                disabled={pendingId !== null}
                onClick={() => {
                  void handleSelect(organization.id);
                }}
              >
                {pendingId === organization.id ? "Selecting" : "Select"}
              </button>
            </article>
          ))}
        </div>
      </div>
    </PageContainer>
  );
}

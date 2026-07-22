import { PageContainer } from "../../components/layout/PageContainer";
import { useAuth } from "./auth-context";

export function TenantContextPage() {
  const auth = useAuth();
  const context = auth.tenantContext;

  return (
    <PageContainer>
      <section className="tenant-page" aria-labelledby="tenant-context-heading">
        <header className="tenant-page__header">
          <p className="auth-eyebrow">Tenant diagnostics</p>
          <h1 id="tenant-context-heading">Tenant context</h1>
        </header>
        {context === null ? (
          <p className="tenant-page__empty">No organization context is selected.</p>
        ) : (
          <dl className="tenant-grid">
            <div>
              <dt>User</dt>
              <dd>{context.user_id}</dd>
            </div>
            <div>
              <dt>Organization</dt>
              <dd>{context.organization_id}</dd>
            </div>
            <div>
              <dt>Membership</dt>
              <dd>{context.membership_id}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{context.role}</dd>
            </div>
            <div className="tenant-grid__wide">
              <dt>Permissions</dt>
              <dd>{context.permissions.join(", ")}</dd>
            </div>
          </dl>
        )}
      </section>
    </PageContainer>
  );
}

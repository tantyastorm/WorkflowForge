import { PageContainer } from "../../components/layout/PageContainer";

export function HomePage() {
  return (
    <PageContainer>
      <div className="home-page">
        <p className="home-page__eyebrow">Frontend foundation</p>
        <h1>WorkflowForge</h1>
        <p className="home-page__lead">
          The repository foundation is under active development. This shell is ready for routing,
          typed API access, and the system-status view coming next.
        </p>
        <div className="home-page__note" aria-label="Next foundation area">
          System status integration will appear here in the next Phase 1 commit.
        </div>
      </div>
    </PageContainer>
  );
}

import { ErrorState } from "../../components/feedback/ErrorState";
import { PageContainer } from "../../components/layout/PageContainer";

export function ForbiddenPage() {
  return (
    <PageContainer>
      <ErrorState
        title="Access denied"
        message="Your current organization role does not include permission for this page."
      />
    </PageContainer>
  );
}

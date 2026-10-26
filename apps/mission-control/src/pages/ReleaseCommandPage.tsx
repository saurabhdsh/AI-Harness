import { EmptyState, PageHeader } from "../components/ui";

export function ReleaseCommandPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Delivery"
        title="Release Command"
        subtitle="Promote agents across environments with gated release trains."
      />
      <EmptyState
        title="Release Command is planned"
        body="No /api/v1/releases endpoints are available yet. This surface will wire to promotion workflows, environment gates, and rollback once the control-plane ships them."
      />
    </div>
  );
}

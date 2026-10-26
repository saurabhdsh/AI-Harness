import { EmptyState, PageHeader } from "../components/ui";

export function WorkflowsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Orchestration"
        title="Workflow Orchestration"
        subtitle="Multi-agent pipelines and human-in-the-loop graphs."
      />
      <EmptyState
        title="Workflow Orchestration is planned"
        body="No /api/v1/workflows endpoints exist yet. This page will host DAG editors, run history, and pause/resume controls when the orchestration service lands."
      />
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { AgentConstellation } from "../components/AgentConstellation";
import { ErrorState, MetricCard, PageHeader, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import type { Agent, MissionOverview } from "../lib/types";

export function MissionControlPage() {
  const overview = useQuery({
    queryKey: ["mission-overview"],
    queryFn: () => api<MissionOverview>("/api/v1/mission/overview"),
  });

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=100"),
  });

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Mission Control"
        subtitle="Live posture across the federated agent estate."
      />

      {overview.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}
      {overview.isError && <ErrorState error={overview.error} />}
      {overview.data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Total agents" value={overview.data.total_agents} />
          <MetricCard
            label="Recent executions"
            value={overview.data.recent_executions}
            hint="Across the control plane"
          />
          <MetricCard
            label="Failed (24h)"
            value={overview.data.failed_executions_24h}
            hint="Invocation failures"
          />
          <MetricCard
            label="Pending approvals"
            value={overview.data.pending_approvals}
            hint={`Cost $${overview.data.total_cost_usd.toFixed(2)}`}
          />
        </div>
      )}

      {overview.data && (
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <MetricCard
            label="By health"
            value={
              <span className="text-base font-medium">
                {Object.entries(overview.data.by_health)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || "—"}
              </span>
            }
          />
          <MetricCard
            label="By lifecycle"
            value={
              <span className="text-base font-medium">
                {Object.entries(overview.data.by_lifecycle)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || "—"}
              </span>
            }
          />
          <MetricCard
            label="By evaluation"
            value={
              <span className="text-base font-medium">
                {Object.entries(overview.data.by_evaluation)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ") || "—"}
              </span>
            }
          />
        </div>
      )}

      <section className="mt-10">
        <h2 className="mb-4 text-[15px] font-semibold text-[var(--ink)]">Agent topology</h2>
        {agents.isLoading && <Skeleton className="h-48" />}
        {agents.isError && <ErrorState error={agents.error} />}
        {agents.data && <AgentConstellation agents={agents.data} />}
      </section>
    </div>
  );
}

import { Link } from "react-router-dom";
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
        subtitle="Live posture across the federated agent estate — inventory, usage, and invoke health."
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
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Agent registry"
              value={overview.data.total_agents}
              hint="Inventory count"
            />
            <MetricCard
              label="Active users"
              value={overview.data.active_users_30d ?? 0}
              hint="Distinct invoke actors · 30d"
            />
            <MetricCard
              label="Agent run-time"
              value={`${(overview.data.agent_runtime_hours_30d ?? 0).toFixed(2)} h`}
              hint="Invoke + federated runtime · 30d"
            />
            <MetricCard
              label="Registry sync"
              value={overview.data.registry_sync?.platforms_synced ?? 0}
              hint={`${overview.data.registry_sync?.connected_platforms ?? 0} platforms · obs ${overview.data.registry_sync?.collect_observability_enabled ?? 0}`}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Sessions (30d)"
              value={overview.data.sessions_30d ?? 0}
              hint="Activity sessions / invokes"
            />
            <MetricCard
              label="Exceptions (30d)"
              value={overview.data.exceptions_30d ?? 0}
              hint="Failed sessions"
            />
            <MetricCard
              label="Agents without owners"
              value={overview.data.agents_without_owners ?? 0}
              hint="Governance gap"
            />
            <MetricCard
              label="Pending approvals"
              value={overview.data.pending_approvals}
              hint={`Cost $${overview.data.total_cost_usd.toFixed(2)}`}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Recent executions"
              value={overview.data.recent_executions}
              hint="Last 24h"
            />
            <MetricCard
              label="Failed (24h)"
              value={overview.data.failed_executions_24h}
              hint="Invocation failures"
            />
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
          </div>

          {(overview.data.registry_sync?.platforms?.length ?? 0) > 0 && (
            <section className="mt-8 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-[15px] font-semibold">Connected platform sync</h2>
                <Link to="/platforms" className="text-[13px] text-[var(--accent)] hover:underline">
                  Manage →
                </Link>
              </div>
              <div className="space-y-2 text-[13px]">
                {overview.data.registry_sync!.platforms.map((p) => (
                  <div
                    key={p.id}
                    className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line-soft)] py-2 last:border-0"
                  >
                    <div>
                      <span className="font-medium">{p.name}</span>
                      <span className="ml-2 font-mono text-[11px] text-[var(--ink-muted)]">
                        {p.connector_type}
                      </span>
                    </div>
                    <div className="text-[12px] text-[var(--ink-muted)]">
                      {p.synced_agent_count} agents
                      {p.last_synced_at
                        ? ` · ${new Date(p.last_synced_at).toLocaleString()}`
                        : " · never synced"}
                      {p.collect_observability ? " · obs on" : " · obs off"}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
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

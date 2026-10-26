import { useQuery } from "@tanstack/react-query";
import {
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Execution, MissionOverview } from "../lib/types";

export function ReliabilityPage() {
  const overview = useQuery({
    queryKey: ["mission-overview"],
    queryFn: () => api<MissionOverview>("/api/v1/mission/overview"),
  });
  const executions = useQuery({
    queryKey: ["executions-all"],
    queryFn: () => api<Execution[]>("/api/v1/executions?limit=50"),
  });

  const failed = (executions.data ?? []).filter((e) => e.status.toLowerCase() === "failed");

  return (
    <div>
      <PageHeader
        eyebrow="Resilience"
        title="Reliability Center"
        subtitle="Failure signal derived from real executions — no synthetic SLOs."
      />

      {overview.isLoading && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      )}
      {overview.isError && <ErrorState error={overview.error} />}
      {overview.data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <MetricCard label="Failed (24h)" value={overview.data.failed_executions_24h} />
          <MetricCard label="Recent executions" value={overview.data.recent_executions} />
          <MetricCard
            label="Unhealthy agents"
            value={overview.data.by_health.unhealthy ?? overview.data.by_health.degraded ?? 0}
            hint="From mission overview health buckets"
          />
        </div>
      )}

      <section className="mt-8">
        <h2 className="mb-3 text-[15px] font-semibold">Recent failures</h2>
        {executions.isLoading && <Skeleton className="h-32" />}
        {executions.isError && <ErrorState error={executions.error} />}
        {executions.data && failed.length === 0 && (
          <EmptyState
            title="No failed executions in the latest window"
            body="Dedicated SLO / incident APIs are planned. This view only reflects live execution status."
          />
        )}
        {failed.length > 0 && (
          <div className="space-y-2">
            {failed.map((e) => (
              <div
                key={e.id}
                className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-white px-4 py-3"
              >
                <div>
                  <div className="font-mono text-[12px]">{e.id}</div>
                  <div className="text-[11px] text-red-600">{e.error ?? "Failed"}</div>
                </div>
                <StatusBadge status={e.status} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

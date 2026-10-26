import { useQuery } from "@tanstack/react-query";
import {
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  Skeleton,
} from "../components/ui";
import { api } from "../lib/api";
import type { Budget, CostRecord, CostSummary } from "../lib/types";

export function FinOpsPage() {
  const summary = useQuery({
    queryKey: ["costs-summary"],
    queryFn: () => api<CostSummary>("/api/v1/costs/summary"),
  });
  const records = useQuery({
    queryKey: ["costs"],
    queryFn: () => api<CostRecord[]>("/api/v1/costs"),
  });
  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: () => api<Budget[]>("/api/v1/costs/budgets"),
  });

  return (
    <div>
      <PageHeader
        eyebrow="Spend"
        title="FinOps Intelligence"
        subtitle="Live cost and budget data from the control plane."
      />

      {summary.isLoading && (
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}
      {summary.isError && <ErrorState error={summary.error} />}
      {summary.data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Total cost"
            value={`$${summary.data.total_cost_usd.toFixed(4)}`}
          />
          <MetricCard label="Input tokens" value={summary.data.total_token_input} />
          <MetricCard label="Output tokens" value={summary.data.total_token_output} />
          <MetricCard label="Records" value={summary.data.records} />
        </div>
      )}

      <section className="mt-8">
        <h2 className="mb-3 text-[15px] font-semibold">Budgets</h2>
        {budgets.isLoading && <Skeleton className="h-24" />}
        {budgets.isError && <ErrorState error={budgets.error} />}
        {budgets.data && budgets.data.length === 0 && (
          <EmptyState title="No budgets configured" body="Budget records will appear from GET /api/v1/costs/budgets." />
        )}
        {budgets.data && budgets.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {budgets.data.map((b) => (
              <div
                key={b.id}
                className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-[var(--shadow-sm)]"
              >
                <div className="font-medium">{b.name}</div>
                <div className="mt-1 text-[12px] text-[var(--ink-muted)]">
                  {b.scope} · {b.period}
                </div>
                <div className="mt-3 text-[13px] tabular">
                  ${b.spent_usd.toFixed(2)} / ${b.limit_usd.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-[15px] font-semibold">Cost records</h2>
        {records.isLoading && <Skeleton className="h-24" />}
        {records.isError && <ErrorState error={records.error} />}
        {records.data && records.data.length === 0 && (
          <EmptyState
            title="No cost records"
            body="Costs accumulate when agents are invoked with token metering."
          />
        )}
        {records.data && records.data.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-[var(--line)] bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                <tr>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {records.data.map((r) => (
                  <tr key={r.id} className="border-b border-[var(--line-soft)] last:border-0">
                    <td className="px-4 py-3 text-[var(--ink-muted)]">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px]">{r.model_name ?? "—"}</td>
                    <td className="px-4 py-3 tabular">${r.cost_usd.toFixed(6)}</td>
                    <td className="px-4 py-3 tabular text-[var(--ink-muted)]">
                      {r.token_input}/{r.token_output}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

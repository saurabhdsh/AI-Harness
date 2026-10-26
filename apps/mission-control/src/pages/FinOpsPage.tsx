import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Budget, CostRecord, CostSummary } from "../lib/types";

function BudgetCard({ b }: { b: Budget }) {
  const spent = b.computed_spent_usd ?? b.spent_usd;
  const pct = Math.min(100, Math.round((b.pct_used ?? 0) * 100));
  const warn = Boolean(b.over_threshold);

  return (
    <div
      className={`rounded-2xl border bg-white p-4 shadow-[var(--shadow-sm)] ${
        warn ? "border-amber-300" : "border-[var(--line)]"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-[13px]">{b.name}</div>
          <div className="mt-0.5 text-[11px] text-[var(--ink-muted)]">
            {b.scope}
            {b.agent_name ? ` · ${b.agent_name}` : ""} · {b.period}
            {!b.is_active ? " · inactive" : ""}
          </div>
        </div>
        {warn ? <StatusBadge status="degraded" /> : <StatusBadge status="healthy" />}
      </div>
      <div className="mt-3 flex items-end justify-between gap-2">
        <div className="text-[13px] tabular">
          ${spent.toFixed(4)}
          <span className="text-[var(--ink-muted)]"> / ${b.limit_usd.toFixed(2)}</span>
        </div>
        <div className="text-[12px] font-semibold tabular text-[var(--ink-muted)]">{pct}%</div>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-muted)]">
        <div
          className={`h-full rounded-full transition-all ${warn ? "bg-amber-500" : "bg-emerald-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-[var(--ink-muted)]">
        <span>Remaining ${Number(b.remaining_usd ?? Math.max(b.limit_usd - spent, 0)).toFixed(4)}</span>
        <span>Alert @ {Math.round((b.alert_threshold ?? 0.8) * 100)}%</span>
      </div>
    </div>
  );
}

export function FinOpsPage() {
  const summary = useQuery({
    queryKey: ["costs-summary"],
    queryFn: () => api<CostSummary>("/api/v1/costs/summary"),
    refetchInterval: 10_000,
  });
  const records = useQuery({
    queryKey: ["costs"],
    queryFn: () => api<CostRecord[]>("/api/v1/costs?limit=100"),
    refetchInterval: 10_000,
  });
  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: () => api<Budget[]>("/api/v1/costs/budgets"),
    refetchInterval: 10_000,
  });

  const activeBudgets = (budgets.data ?? []).filter((b) => b.is_active);
  const overCount =
    summary.data?.budgets_over_threshold ??
    activeBudgets.filter((b) => b.over_threshold).length;

  return (
    <div>
      <PageHeader
        eyebrow="Spend"
        title="FinOps Intelligence"
        subtitle="Live cost vs budget from the control plane. Rates are estimated placeholders, not invoices."
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
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Total spend (est.)"
              value={`$${summary.data.total_cost_usd.toFixed(4)}`}
              hint="From agent invokes in this tenant"
            />
            <MetricCard
              label="Tokens in / out"
              value={`${summary.data.total_token_input.toLocaleString()} / ${summary.data.total_token_output.toLocaleString()}`}
              hint={`${summary.data.records} invoke cost records`}
            />
            <MetricCard
              label="Avg cost / invoke"
              value={
                summary.data.records
                  ? `$${(summary.data.total_cost_usd / summary.data.records).toFixed(4)}`
                  : "$0.0000"
              }
            />
            <MetricCard
              label="Budgets over alert"
              value={overCount}
              hint={`${summary.data.active_budgets ?? activeBudgets.length} active budgets`}
            />
          </div>
          <p className="mt-3 text-[12px] text-[var(--ink-muted)]">
            {summary.data.rate_note ?? "Estimated rates — not provider invoices"}. Spend is
            attributed from invoke logs (provider usage when present, otherwise size-based
            estimate).
          </p>
        </>
      )}

      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-[15px] font-semibold">Budgets</h2>
          <Link
            to="/admin"
            className="text-[12px] font-medium text-[var(--accent)] hover:underline"
          >
            Configure in Admin →
          </Link>
        </div>
        {budgets.isLoading && <Skeleton className="h-24" />}
        {budgets.isError && <ErrorState error={budgets.error} />}
        {budgets.data && budgets.data.length === 0 && (
          <EmptyState
            title="No budgets configured"
            body="An admin can set tenant or agent spend caps under Administration → FinOps budgets."
          />
        )}
        {activeBudgets.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {activeBudgets.map((b) => (
              <BudgetCard key={b.id} b={b} />
            ))}
          </div>
        )}
        {budgets.data &&
          budgets.data.some((b) => !b.is_active) &&
          activeBudgets.length === 0 && (
            <EmptyState
              title="No active budgets"
              body="All budgets are deactivated. Create or re-enable one in Administration."
            />
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
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3">Tokens in/out</th>
                </tr>
              </thead>
              <tbody>
                {records.data.map((r) => (
                  <tr key={r.id} className="border-b border-[var(--line-soft)] last:border-0">
                    <td className="px-4 py-3 text-[var(--ink-muted)]">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-[13px]">
                      {r.agent_name ?? (r.agent_id ? `${r.agent_id.slice(0, 8)}…` : "—")}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px]">{r.model_name ?? "—"}</td>
                    <td className="px-4 py-3 font-medium tabular">
                      ${r.cost_usd.toFixed(4)}
                      {Boolean(r.metadata?.tokens_estimated) && (
                        <span className="ml-1 text-[10px] font-normal text-[var(--ink-muted)]">
                          est.
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 tabular text-[var(--ink-muted)]">
                      {r.token_input.toLocaleString()} / {r.token_output.toLocaleString()}
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

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { ReliabilityOverview } from "../lib/types";

const WINDOWS = [
  { hours: 1, label: "1h" },
  { hours: 6, label: "6h" },
  { hours: 24, label: "24h" },
  { hours: 168, label: "7d" },
] as const;

const CLASS_COLORS: Record<string, string> = {
  timeout: "#f59e0b",
  connection: "#ef4444",
  http_5xx: "#dc2626",
  http_4xx: "#ea580c",
  unsupported: "#8b5cf6",
  auth: "#db2777",
  validation: "#2563eb",
  other: "#64748b",
  unknown: "#94a3b8",
};

function pct(n: number) {
  return `${(n * 100).toFixed(n >= 0.1 || n === 0 ? 0 : 1)}%`;
}

function ms(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}s`;
  return `${Math.round(n)} ms`;
}

function truncate(s: string | null | undefined, n = 96) {
  if (!s) return "—";
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

export function ReliabilityPage() {
  const [windowHours, setWindowHours] = useState(24);
  const [selectedClass, setSelectedClass] = useState<string | null>(null);

  const reliability = useQuery({
    queryKey: ["reliability", windowHours],
    queryFn: () =>
      api<ReliabilityOverview>(`/api/v1/reliability/overview?window_hours=${windowHours}`),
    refetchInterval: 8_000,
  });

  const data = reliability.data;

  const filteredFailures = useMemo(() => {
    const rows = data?.recent_failures ?? [];
    if (!selectedClass) return rows;
    return rows.filter((f) => f.error_class === selectedClass);
  }, [data?.recent_failures, selectedClass]);

  const posture = useMemo(() => {
    if (!data) return null;
    if (data.total_executions === 0) return { label: "No signal", tone: "muted" as const };
    if (data.error_rate >= 0.25 || data.unhealthy_agents > 0)
      return { label: "Elevated risk", tone: "bad" as const };
    if (data.error_rate >= 0.08 || data.degraded_agents > 0)
      return { label: "Watch", tone: "warn" as const };
    return { label: "Stable", tone: "good" as const };
  }, [data]);

  return (
    <div className="w-full min-w-0 max-w-full">
      <PageHeader
        eyebrow="Resilience"
        title="Reliability Center"
        subtitle="Failure signal derived from real executions — no synthetic SLOs."
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {WINDOWS.map((w) => (
          <button
            key={w.hours}
            type="button"
            onClick={() => setWindowHours(w.hours)}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
              windowHours === w.hours
                ? "bg-[#1d1d1f] text-white"
                : "border border-[var(--line)] bg-white text-[var(--ink-muted)] hover:bg-[var(--bg-muted)]"
            }`}
          >
            {w.label}
          </button>
        ))}
        <span className="w-full text-[11px] text-[var(--ink-muted)] sm:ml-auto sm:w-auto">
          Auto-refresh · /api/v1/reliability/overview
        </span>
      </div>

      {reliability.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}
      {reliability.isError && <ErrorState error={reliability.error} />}

      {data && (
        <>
          {/* Posture strip */}
          <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-5 py-4 shadow-[var(--shadow-sm)]">
            <div
              className={`inline-flex items-center rounded-full px-3 py-1 text-[12px] font-semibold ${
                posture?.tone === "good"
                  ? "bg-emerald-50 text-emerald-800"
                  : posture?.tone === "warn"
                    ? "bg-amber-50 text-amber-800"
                    : posture?.tone === "bad"
                      ? "bg-red-50 text-red-800"
                      : "bg-[var(--bg-muted)] text-[var(--ink-muted)]"
              }`}
            >
              {posture?.label}
            </div>
            <div className="text-[13px] text-[var(--ink-muted)]">
              {data.total_executions === 0
                ? "No invokes in this window yet."
                : `${data.failed} failures of ${data.total_executions} invokes · ${data.agents_invoked} agents active`}
            </div>
            <div className="ml-auto text-[11px] tabular text-[var(--ink-faint)]">
              Window from {new Date(data.window_start).toLocaleString()}
            </div>
          </div>

          {/* KPI row */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Error rate"
              value={pct(data.error_rate)}
              hint={`${data.failed} failed · ${data.succeeded} succeeded`}
            />
            <MetricCard
              label="Success rate"
              value={pct(data.success_rate)}
              hint={data.running ? `${data.running} still running` : "Completed invokes"}
            />
            <MetricCard
              label="Latency p95"
              value={ms(data.p95_latency_ms)}
              hint={`Avg ${ms(data.avg_latency_ms)} · max ${ms(data.max_latency_ms)}`}
            />
            <MetricCard
              label="Agent health"
              value={data.unhealthy_agents + data.degraded_agents}
              hint={`${data.unhealthy_agents} unhealthy · ${data.degraded_agents} degraded`}
            />
          </div>
          <p className="mt-3 text-[12px] text-[var(--ink-muted)]">{data.note}</p>

          {/* Charts row */}
          <div className="mt-8 grid min-w-0 gap-6 lg:grid-cols-5">
            <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)] lg:col-span-3">
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <h2 className="text-[15px] font-semibold">Failure timeline</h2>
                <span className="text-[11px] text-[var(--ink-muted)]">Succeeded vs failed</span>
              </div>
              <div className="mt-4 h-56 min-w-0">
                {data.total_executions === 0 ? (
                  <EmptyChart />
                ) : (
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart data={data.timeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#f2f2f7" vertical={false} />
                      <XAxis
                        dataKey="t"
                        tick={{ fontSize: 10, fill: "#86868b" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 10, fill: "#86868b" }}
                        axisLine={false}
                        tickLine={false}
                        width={28}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid #e5e5ea",
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="ok" name="Succeeded" stackId="a" fill="#34d399" />
                      <Bar
                        dataKey="fail"
                        name="Failed"
                        stackId="a"
                        fill="#f87171"
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)] lg:col-span-2">
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <h2 className="text-[15px] font-semibold">Error classes</h2>
                <button
                  type="button"
                  className="text-[11px] text-[var(--accent)] hover:underline disabled:opacity-40"
                  disabled={!selectedClass}
                  onClick={() => setSelectedClass(null)}
                >
                  Clear filter
                </button>
              </div>
              <p className="text-[12px] text-[var(--ink-muted)]">
                Classified from recorded error text — click to filter the stream.
              </p>
              {data.error_classes.length === 0 ? (
                <div className="mt-6">
                  <EmptyState
                    title="No failures to classify"
                    body="Invoke agents; failed runs appear here with taxonomy."
                  />
                </div>
              ) : (
                <ul className="mt-4 space-y-2">
                  {data.error_classes.map((c) => {
                    const active = selectedClass === c.class_id;
                    const color = CLASS_COLORS[c.class_id] ?? "#64748b";
                    return (
                      <li key={c.class_id}>
                        <button
                          type="button"
                          onClick={() =>
                            setSelectedClass(active ? null : c.class_id)
                          }
                          className={`w-full rounded-xl border px-3 py-2.5 text-left transition ${
                            active
                              ? "border-[#1d1d1f] bg-[var(--bg-muted)]"
                              : "border-[var(--line)] hover:bg-[var(--bg-muted)]"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-2 text-[13px] font-medium">
                              <span
                                className="inline-block h-2 w-2 rounded-full"
                                style={{ background: color }}
                              />
                              {c.label}
                            </span>
                            <span className="tabular text-[12px] text-[var(--ink-muted)]">
                              {c.count} · {pct(c.share)}
                            </span>
                          </div>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.max(4, Math.round(c.share * 100))}%`,
                                background: color,
                              }}
                            />
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>

          {/* Agents at risk + latency */}
          <div className="mt-8 grid min-w-0 gap-6 xl:grid-cols-2">
            <section className="min-w-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-sm)]">
              <div className="border-b border-[var(--line)] px-5 py-4">
                <h2 className="text-[15px] font-semibold">Agents at risk</h2>
                <p className="mt-0.5 text-[12px] text-[var(--ink-muted)]">
                  Ranked by error rate from invokes in this window.
                </p>
              </div>
              {data.agents_at_risk.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    title="No failing agents"
                    body="Agents with failed invokes in the window show up here."
                  />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[13px]">
                    <thead className="bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.1em] text-[var(--ink-muted)]">
                      <tr>
                        <th className="px-4 py-2.5 font-medium">Agent</th>
                        <th className="px-3 py-2.5 font-medium">Health</th>
                        <th className="px-3 py-2.5 font-medium tabular">Fails</th>
                        <th className="px-3 py-2.5 font-medium tabular">Rate</th>
                        <th className="px-4 py-2.5 font-medium">Last error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.agents_at_risk.map((a) => (
                        <tr key={a.agent_id} className="border-t border-[var(--line-soft)]">
                          <td className="px-4 py-3">
                            <Link
                              to={`/agents/${a.agent_id}`}
                              className="font-medium text-[var(--ink)] hover:text-[var(--accent)]"
                            >
                              {a.agent_name}
                            </Link>
                            <div className="text-[11px] text-[var(--ink-muted)]">
                              {a.domain ?? "—"} · {a.succeeded}/{a.total} ok
                            </div>
                          </td>
                          <td className="px-3 py-3">
                            <StatusBadge status={a.health_status} />
                          </td>
                          <td className="px-3 py-3 tabular">{a.failed}</td>
                          <td className="px-3 py-3 tabular font-medium text-red-700">
                            {pct(a.error_rate)}
                          </td>
                          <td className="max-w-[220px] px-4 py-3 text-[12px] text-[var(--ink-muted)]">
                            {truncate(a.last_error, 72)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="min-w-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-sm)]">
              <div className="border-b border-[var(--line)] px-5 py-4">
                <h2 className="text-[15px] font-semibold">Latency outliers</h2>
                <p className="mt-0.5 text-[12px] text-[var(--ink-muted)]">
                  Slowest recorded invokes — measured latency, not an SLO target.
                </p>
              </div>
              {data.latency_outliers.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    title="No latency samples"
                    body="Outliers appear once executions report latency_ms."
                  />
                </div>
              ) : (
                <ul className="divide-y divide-[var(--line-soft)]">
                  {data.latency_outliers.map((o) => (
                    <li
                      key={o.execution_id}
                      className="flex items-center justify-between gap-3 px-5 py-3"
                    >
                      <div className="min-w-0">
                        <Link
                          to={`/agents/${o.agent_id}`}
                          className="text-[13px] font-medium hover:text-[var(--accent)]"
                        >
                          {o.agent_name}
                        </Link>
                        <div className="font-mono text-[11px] text-[var(--ink-muted)]">
                          {o.execution_id.slice(0, 8)}… ·{" "}
                          {new Date(o.created_at).toLocaleString()}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <StatusBadge status={o.status} />
                        <span className="tabular text-[13px] font-semibold">{ms(o.latency_ms)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Failure stream */}
          <section className="mt-8 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-sm)]">
            <div className="flex flex-wrap items-end justify-between gap-2 border-b border-[var(--line)] px-5 py-4">
              <div>
                <h2 className="text-[15px] font-semibold">Failure stream</h2>
                <p className="mt-0.5 text-[12px] text-[var(--ink-muted)]">
                  {selectedClass
                    ? `Filtered to ${selectedClass.replaceAll("_", " ")}`
                    : "Newest failed executions first"}
                </p>
              </div>
              <Link
                to="/observatory"
                className="text-[12px] font-medium text-[var(--accent)] hover:underline"
              >
                Open Live Observatory →
              </Link>
            </div>
            {filteredFailures.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No failures in this view"
                  body={
                    selectedClass
                      ? "Try another error class or clear the filter."
                      : "When an invoke fails, the error and agent appear here."
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.1em] text-[var(--ink-muted)]">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">When</th>
                      <th className="px-3 py-2.5 font-medium">Agent</th>
                      <th className="px-3 py-2.5 font-medium">Class</th>
                      <th className="px-3 py-2.5 font-medium">Error</th>
                      <th className="px-4 py-2.5 font-medium tabular">Latency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFailures.map((f) => (
                      <tr key={f.execution_id} className="border-t border-[var(--line-soft)] align-top">
                        <td className="whitespace-nowrap px-4 py-3 text-[12px] text-[var(--ink-muted)]">
                          {new Date(f.created_at).toLocaleString()}
                        </td>
                        <td className="px-3 py-3">
                          <Link
                            to={`/agents/${f.agent_id}`}
                            className="font-medium hover:text-[var(--accent)]"
                          >
                            {f.agent_name}
                          </Link>
                          <div className="font-mono text-[10px] text-[var(--ink-faint)]">
                            {f.execution_id.slice(0, 8)}…
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span
                            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] px-2 py-0.5 text-[11px] font-medium"
                          >
                            <span
                              className="h-1.5 w-1.5 rounded-full"
                              style={{
                                background: CLASS_COLORS[f.error_class] ?? "#94a3b8",
                              }}
                            />
                            {f.error_class.replaceAll("_", " ")}
                          </span>
                        </td>
                        <td className="max-w-md px-3 py-3 text-[12px] text-red-700">
                          {truncate(f.error, 140)}
                        </td>
                        <td className="px-4 py-3 tabular text-[var(--ink-muted)]">
                          {ms(f.latency_ms)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center text-[13px] text-[var(--ink-muted)]">
      No execution volume in this window
    </div>
  );
}

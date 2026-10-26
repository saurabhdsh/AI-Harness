import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Button,
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import { computeObservabilityStats } from "../lib/observabilityStats";
import type { Execution, Trace } from "../lib/types";

type Filter = "all" | "succeeded" | "failed";
const CHART = "#d97757";
const BLUE = "#0071e3";

export function LiveObservatoryPage() {
  const [selected, setSelected] = useState<Execution | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [autoPicked, setAutoPicked] = useState(false);
  const [windowMinutes, setWindowMinutes] = useState(1440);

  const executions = useQuery({
    queryKey: ["executions-all"],
    queryFn: () => api<Execution[]>("/api/v1/executions?limit=200"),
    refetchInterval: 4000,
  });

  const stats = useMemo(
    () => computeObservabilityStats(executions.data ?? [], windowMinutes),
    [executions.data, windowMinutes],
  );

  const filtered = useMemo(() => {
    const rows = executions.data ?? [];
    if (filter === "succeeded") return rows.filter((e) => e.status === "succeeded");
    if (filter === "failed") return rows.filter((e) => e.status === "failed");
    return rows;
  }, [executions.data, filter]);

  const latestSuccess = useMemo(
    () => (executions.data ?? []).find((e) => e.status === "succeeded") ?? null,
    [executions.data],
  );

  const outcomePie = useMemo(
    () => [
      { name: "Succeeded", value: stats.succeeded, color: "#34d399" },
      { name: "Failed", value: stats.failed, color: "#f87171" },
      { name: "Other", value: Math.max(0, stats.total - stats.succeeded - stats.failed), color: "#c7c7cc" },
    ].filter((d) => d.value > 0),
    [stats],
  );

  useEffect(() => {
    if (autoPicked || !executions.data?.length) return;
    const pick =
      executions.data.find((e) => e.status === "succeeded") ?? executions.data[0] ?? null;
    if (pick) {
      setSelected(pick);
      setAutoPicked(true);
    }
  }, [executions.data, autoPicked]);

  const traceKey = selected?.id ?? null;
  const trace = useQuery({
    queryKey: ["trace", traceKey],
    queryFn: () => api<Trace>(`/api/v1/traces/${traceKey}`),
    enabled: Boolean(traceKey),
  });

  return (
    <div className="w-full min-w-0 max-w-full overflow-x-hidden">
      <PageHeader
        eyebrow="Observability"
        title="Live Observatory"
        subtitle="Real execution telemetry — performance, reliability, tokens, and trace waterfalls from the control plane."
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        {[
          { id: 60, label: "1h" },
          { id: 360, label: "6h" },
          { id: 1440, label: "24h" },
          { id: 10080, label: "7d" },
        ].map((w) => (
          <button
            key={w.id}
            type="button"
            onClick={() => setWindowMinutes(w.id)}
            className={`rounded-full px-3 py-1 text-[12px] font-medium ${
              windowMinutes === w.id
                ? "bg-[#1d1d1f] text-white"
                : "bg-[var(--bg-muted)] text-[var(--ink-muted)] hover:bg-white"
            }`}
          >
            {w.label}
          </button>
        ))}
        <span className="w-full text-[11px] text-[var(--ink-muted)] sm:ml-auto sm:w-auto">
          Auto-refresh · sourced from /api/v1/executions
        </span>
      </div>

      {executions.isLoading && <Skeleton className="mb-6 h-40" />}
      {executions.isError && <ErrorState error={executions.error} />}

      {executions.data && (
        <>
          {/* KPI strip — 2×2 until wide screens */}
          <div className="mb-6 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Invocations"
              value={<CountUp value={stats.total} />}
              hint={`${stats.uniqueAgents} agent(s) · window ${stats.recentWindowMinutes >= 1440 ? `${stats.recentWindowMinutes / 1440}d` : `${stats.recentWindowMinutes}m`}`}
            />
            <MetricCard
              label="Success rate"
              value={`${stats.successRate.toFixed(1)}%`}
              hint={`${stats.succeeded} ok · ${stats.failed} failed`}
            />
            <MetricCard
              label="Avg latency"
              value={stats.avgLatency != null ? `${Math.round(stats.avgLatency)}` : "—"}
              hint={stats.avgLatency != null ? "ms · real invoke timings" : "No latency samples yet"}
            />
            <MetricCard
              label="p95 latency"
              value={stats.p95 != null ? `${Math.round(stats.p95)}` : "—"}
              hint={
                stats.p50 != null
                  ? `p50 ${Math.round(stats.p50)} · p99 ${stats.p99 != null ? Math.round(stats.p99) : "—"} ms`
                  : "Awaiting executions"
              }
            />
          </div>

          {/* Charts stack vertically on laptop, 2-col only on very wide */}
          <div className="mb-6 grid min-w-0 grid-cols-1 gap-6 xl:grid-cols-2">
            <Panel title="Performance" subtitle="Latency over time">
              <ChartFrame>
                {stats.timeline.every((p) => p.latency === 0 && p.ok === 0 && p.fail === 0) ? (
                  <EmptyChart />
                ) : (
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <AreaChart data={stats.timeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="latFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={CHART} stopOpacity={0.35} />
                          <stop offset="100%" stopColor={CHART} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#f2f2f7" vertical={false} />
                      <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} width={36} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Area
                        type="monotone"
                        dataKey="latency"
                        name="Avg latency (ms)"
                        stroke={CHART}
                        fill="url(#latFill)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </ChartFrame>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <MiniStat label="Min" value={fmtMs(stats.minLatency)} />
                <MiniStat label="Avg" value={fmtMs(stats.avgLatency)} />
                <MiniStat label="Max" value={fmtMs(stats.maxLatency)} />
              </div>
            </Panel>

            <Panel title="Latency histogram" subtitle="Distribution of invoke duration">
              <ChartFrame>
                {stats.latencyBuckets.every((b) => b.count === 0) ? (
                  <EmptyChart />
                ) : (
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart data={stats.latencyBuckets} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="#f2f2f7" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} width={28} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Bar dataKey="count" name="Executions" radius={[6, 6, 0, 0]} fill={BLUE} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </ChartFrame>
            </Panel>

            <Panel title="Reliability" subtitle="Outcome mix + error budget signal">
              <div className="flex min-w-0 flex-col items-stretch gap-4 sm:flex-row sm:items-center">
                <div className="mx-auto h-40 w-40 shrink-0 sm:mx-0">
                  {outcomePie.length === 0 ? (
                    <EmptyChart />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                      <PieChart>
                        <Pie data={outcomePie} dataKey="value" innerRadius={42} outerRadius={68} paddingAngle={3}>
                          {outcomePie.map((d) => (
                            <Cell key={d.name} fill={d.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={tooltipStyle} />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </div>
                <div className="min-w-0 flex-1 space-y-3">
                  <ReliabilityMeter label="Success" value={stats.successRate} good />
                  <ReliabilityMeter label="Error rate" value={stats.errorRate} good={stats.errorRate < 10} invert />
                  <div className="text-[12px] text-[var(--ink-muted)]">
                    Running / pending: <span className="font-semibold text-[var(--ink)]">{stats.running}</span>
                  </div>
                </div>
              </div>
            </Panel>

            <Panel title="Throughput" subtitle="Succeeded vs failed per slot">
              <ChartFrame>
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart data={stats.timeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="#f2f2f7" vertical={false} />
                    <XAxis dataKey="t" tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#86868b" }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="ok" name="Succeeded" stackId="a" fill="#34d399" />
                    <Bar dataKey="fail" name="Failed" stackId="a" fill="#f87171" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>
          </div>

          <div className="mb-6 min-w-0">
            <Panel title="Token telemetry" subtitle="Attributed from recorded executions (when present)">
              <div className="grid min-w-0 grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricTile label="Input tokens" value={stats.totalTokensIn.toLocaleString()} />
                <MetricTile label="Output tokens" value={stats.totalTokensOut.toLocaleString()} />
                <MetricTile
                  label="Avg in / invoke"
                  value={stats.avgTokensIn != null ? Math.round(stats.avgTokensIn).toLocaleString() : "—"}
                />
                <MetricTile
                  label="Avg out / invoke"
                  value={stats.avgTokensOut != null ? Math.round(stats.avgTokensOut).toLocaleString() : "—"}
                />
              </div>
              <p className="mt-3 text-[11px] text-[var(--ink-muted)]">
                Token fields are real when the connector reports usage; otherwise counts stay at 0 — never fabricated.
              </p>
            </Panel>
          </div>
        </>
      )}

      {/* Executions + waterfall */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(["all", "succeeded", "failed"] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-[12px] font-medium capitalize transition ${
              filter === f
                ? "bg-[#0071e3] text-white"
                : "bg-[var(--bg-muted)] text-[var(--ink-muted)] hover:bg-white"
            }`}
          >
            {f}
          </button>
        ))}
        {latestSuccess && (
          <Button
            variant="soft"
            className="ml-auto"
            onClick={() => {
              setFilter("all");
              setSelected(latestSuccess);
            }}
          >
            Jump to latest success
          </Button>
        )}
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="mb-4 text-[15px] font-semibold">Executions</h2>
          {executions.data && filtered.length === 0 && (
            <EmptyState
              title={filter === "succeeded" ? "No successful executions yet" : "No executions"}
              body="Invoke an agent from Agent Universe or Onboarding Studio."
            />
          )}
          {filtered.length > 0 && (
            <div className="max-h-[520px] space-y-2 overflow-y-auto">
              {filtered.map((ex) => (
                <button
                  key={ex.id}
                  type="button"
                  onClick={() => setSelected(ex)}
                  className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition ${
                    selected?.id === ex.id
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--line)] hover:bg-[var(--bg-muted)]"
                  }`}
                >
                  <div>
                    <div className="font-mono text-[12px]">{ex.id.slice(0, 10)}…</div>
                    <div className="text-[11px] text-[var(--ink-muted)]">
                      agent {ex.agent_id.slice(0, 8)} · {new Date(ex.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={ex.status} />
                    <div className="mt-1 text-[11px] tabular text-[var(--ink-muted)]">
                      {ex.latency_ms != null ? `${ex.latency_ms.toFixed(0)} ms` : "—"}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="mb-4 text-[15px] font-semibold">Trace waterfall</h2>
          {!selected && (
            <p className="text-[13px] text-[var(--ink-muted)]">
              Select an execution to load its trace from the API.
            </p>
          )}
          {selected && trace.isLoading && <Skeleton className="h-40" />}
          {selected && trace.isError && <ErrorState error={trace.error} />}
          {selected && trace.data && (
            <div>
              <div className="mb-4 flex flex-wrap items-center gap-2 text-[12px] text-[var(--ink-muted)]">
                <StatusBadge status={selected.status} />
                <StatusBadge status={trace.data.status} />
                <span className="font-mono">exec {selected.id.slice(0, 8)}…</span>
              </div>
              {selected.status === "failed" && (
                <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                  <div className="font-semibold">Historical failure</div>
                  <p className="mt-1 whitespace-pre-wrap break-words text-amber-800">
                    {selected.error || "Invoke failed"}
                  </p>
                  {latestSuccess && latestSuccess.id !== selected.id && (
                    <button
                      type="button"
                      className="mt-2 text-[12px] font-semibold text-[#0071e3] hover:underline"
                      onClick={() => setSelected(latestSuccess)}
                    >
                      Open latest successful trace →
                    </button>
                  )}
                </div>
              )}
              {(trace.data.spans?.length ? trace.data.spans : []).length === 0 ? (
                <EmptyState title="Empty span list" body="Trace record exists but contains no spans yet." />
              ) : (
                <div className="space-y-2">
                  {trace.data.spans.map((span, i) => {
                    const dur = Number(span.duration_ms ?? span.latency_ms ?? 0);
                    const start = Number(span.start_ms ?? 0);
                    const failed = String(span.status ?? "") === "error" || Boolean(span.error);
                    const width = Math.min(100, Math.max(6, dur / 8 || 12));
                    const offset = Math.min(70, Math.max(0, start / 20));
                    return (
                      <motion.div
                        key={i}
                        className="text-[12px]"
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                      >
                        <div className="mb-1 flex justify-between gap-2">
                          <span className="font-mono text-[var(--ink)]">
                            {String(span.name ?? `span-${i}`)}
                            {failed ? " · error" : ""}
                          </span>
                          <span className="tabular text-[var(--ink-muted)]">
                            {dur ? `${Math.round(dur)} ms` : "—"}
                          </span>
                        </div>
                        <div className="h-2.5 rounded-full bg-[var(--bg-muted)]">
                          <motion.div
                            className={`h-2.5 rounded-full ${failed ? "bg-red-500" : "bg-[#0071e3]"}`}
                            initial={{ width: 0 }}
                            animate={{ width: `${width}%` }}
                            style={{ marginLeft: `${offset}%` }}
                            transition={{ type: "spring", stiffness: 90, damping: 18 }}
                          />
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
              {selected.status === "succeeded" && selected.response && (
                <pre className="mt-4 max-h-48 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px]">
                  {JSON.stringify(selected.response, null, 2)}
                </pre>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const tooltipStyle = {
  borderRadius: 12,
  border: "1px solid #e8e8ed",
  fontSize: 12,
  boxShadow: "0 4px 16px rgba(0,0,0,0.07)",
};

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="min-w-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]"
    >
      <div className="mb-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
          {title}
        </div>
        {subtitle && <div className="mt-0.5 text-[13px] text-[var(--ink-muted)]">{subtitle}</div>}
      </div>
      {children}
    </motion.section>
  );
}

/** Prevents Recharts ResponsiveContainer from blowing out CSS grid width */
function ChartFrame({ children }: { children: ReactNode }) {
  return <div className="h-52 w-full min-w-0 overflow-hidden">{children}</div>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[var(--bg-muted)] px-2 py-2">
      <div className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div className="mt-0.5 text-[13px] font-semibold tabular text-[var(--ink)]">{value}</div>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-muted)] px-3 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular tracking-tightish text-[var(--ink)]">
        {value}
      </div>
    </div>
  );
}

function ReliabilityMeter({
  label,
  value,
  good,
  invert,
}: {
  label: string;
  value: number;
  good?: boolean;
  invert?: boolean;
}) {
  const width = Math.min(100, Math.max(0, value));
  const color = invert
    ? value < 10
      ? "bg-emerald-400"
      : "bg-red-400"
    : good
      ? "bg-emerald-400"
      : "bg-amber-400";
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px]">
        <span className="text-[var(--ink-muted)]">{label}</span>
        <span className="font-semibold tabular text-[var(--ink)]">{value.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--bg-muted)]">
        <motion.div
          className={`h-1.5 rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${width}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
      </div>
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center text-[12px] text-[var(--ink-muted)]">
      No samples in this window
    </div>
  );
}

function fmtMs(v: number | null) {
  return v == null ? "—" : `${Math.round(v)} ms`;
}

function CountUp({ value }: { value: number }) {
  return <span className="tabular">{value}</span>;
}

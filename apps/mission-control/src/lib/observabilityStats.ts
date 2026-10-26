import type { Execution } from "./types";

export type LatencyBucket = { label: string; count: number };
export type TimelinePoint = { t: string; latency: number; ok: number; fail: number };
export type ObservabilityStats = {
  total: number;
  succeeded: number;
  failed: number;
  running: number;
  successRate: number;
  errorRate: number;
  avgLatency: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  maxLatency: number | null;
  minLatency: number | null;
  totalTokensIn: number;
  totalTokensOut: number;
  avgTokensIn: number | null;
  avgTokensOut: number | null;
  uniqueAgents: number;
  latencyBuckets: LatencyBucket[];
  timeline: TimelinePoint[];
  recentWindowMinutes: number;
};

function percentile(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[idx];
}

export function computeObservabilityStats(
  executions: Execution[],
  windowMinutes = 1440,
): ObservabilityStats {
  const now = Date.now();
  const cutoff = now - windowMinutes * 60_000;
  const rows = executions.filter((e) => new Date(e.created_at).getTime() >= cutoff);

  const succeeded = rows.filter((e) => e.status === "succeeded");
  const failed = rows.filter((e) => e.status === "failed");
  const running = rows.filter((e) => e.status === "running" || e.status === "pending");
  const latencies = rows
    .map((e) => e.latency_ms)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v))
    .sort((a, b) => a - b);

  const total = rows.length;
  const successRate = total ? (succeeded.length / total) * 100 : 0;
  const errorRate = total ? (failed.length / total) * 100 : 0;
  const avgLatency = latencies.length
    ? latencies.reduce((a, b) => a + b, 0) / latencies.length
    : null;

  const tokenIn = rows.reduce((s, e) => s + (e.token_input ?? 0), 0);
  const tokenOut = rows.reduce((s, e) => s + (e.token_output ?? 0), 0);
  const withTokens = rows.filter((e) => (e.token_input ?? 0) + (e.token_output ?? 0) > 0);

  const agents = new Set(rows.map((e) => e.agent_id));

  const edges = [50, 100, 250, 500, 1000, 3000, 8000, Infinity];
  const labels = ["≤50", "≤100", "≤250", "≤500", "≤1s", "≤3s", "≤8s", ">8s"];
  const bucketCounts = labels.map(() => 0);
  for (const ms of latencies) {
    const i = edges.findIndex((edge) => ms <= edge);
    bucketCounts[i === -1 ? bucketCounts.length - 1 : i] += 1;
  }
  const latencyBuckets = labels.map((label, i) => ({ label, count: bucketCounts[i] }));

  // Build timeline buckets (last 12 slots)
  const slots = 12;
  const slotMs = Math.max(60_000, (windowMinutes * 60_000) / slots);
  const timeline: TimelinePoint[] = [];
  for (let i = slots - 1; i >= 0; i--) {
    const end = now - i * slotMs;
    const start = end - slotMs;
    const inSlot = rows.filter((e) => {
      const t = new Date(e.created_at).getTime();
      return t >= start && t < end;
    });
    const lats = inSlot
      .map((e) => e.latency_ms)
      .filter((v): v is number => typeof v === "number");
    const avg = lats.length ? lats.reduce((a, b) => a + b, 0) / lats.length : 0;
    timeline.push({
      t: new Date(end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      latency: Math.round(avg),
      ok: inSlot.filter((e) => e.status === "succeeded").length,
      fail: inSlot.filter((e) => e.status === "failed").length,
    });
  }

  return {
    total,
    succeeded: succeeded.length,
    failed: failed.length,
    running: running.length,
    successRate,
    errorRate,
    avgLatency,
    p50: percentile(latencies, 50),
    p95: percentile(latencies, 95),
    p99: percentile(latencies, 99),
    maxLatency: latencies.length ? latencies[latencies.length - 1] : null,
    minLatency: latencies.length ? latencies[0] : null,
    totalTokensIn: tokenIn,
    totalTokensOut: tokenOut,
    avgTokensIn: withTokens.length ? tokenIn / withTokens.length : null,
    avgTokensOut: withTokens.length ? tokenOut / withTokens.length : null,
    uniqueAgents: agents.size,
    latencyBuckets,
    timeline,
    recentWindowMinutes: windowMinutes,
  };
}

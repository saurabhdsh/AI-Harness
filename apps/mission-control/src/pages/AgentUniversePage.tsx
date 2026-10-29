import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AgentConstellation } from "../components/AgentConstellation";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  inputClass,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Agent } from "../lib/types";

export function AgentUniversePage() {
  const [view, setView] = useState<"list" | "constellation">("list");
  const [q, setQ] = useState("");
  const [domain, setDomain] = useState("");
  const [lifecycle, setLifecycle] = useState("");

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=200"),
  });

  const filtered = useMemo(() => {
    const rows = agents.data ?? [];
    return rows.filter((a) => {
      const hay = `${a.name} ${a.platform} ${a.framework} ${a.external_id ?? ""} ${a.owner ?? ""} ${a.team ?? ""} ${a.invoke_url ?? ""}`.toLowerCase();
      if (q && !hay.includes(q.toLowerCase())) return false;
      if (domain && (a.domain ?? "").toLowerCase() !== domain.toLowerCase()) return false;
      if (lifecycle && a.lifecycle_state.toLowerCase() !== lifecycle.toLowerCase()) return false;
      return true;
    });
  }, [agents.data, q, domain, lifecycle]);

  const domains = useMemo(
    () =>
      Array.from(new Set((agents.data ?? []).map((a) => a.domain).filter(Boolean) as string[])).sort(),
    [agents.data],
  );
  const lifecycles = useMemo(
    () =>
      Array.from(new Set((agents.data ?? []).map((a) => a.lifecycle_state))).sort(),
    [agents.data],
  );

  return (
    <div>
      <PageHeader
        eyebrow="Registry inventory"
        title="Agent Registry"
        subtitle="Cross-platform inventory keyed by external_id + invoke_url. Sync from Connected Platforms or CI register after deploy."
      />

      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="min-w-[220px] flex-1">
          <Field label="Search">
            <input
              className={inputClass}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Name, platform, owner…"
            />
          </Field>
        </div>
        <div className="w-40">
          <Field label="Domain">
            <select className={inputClass} value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">All</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="w-44">
          <Field label="Lifecycle">
            <select
              className={inputClass}
              value={lifecycle}
              onChange={(e) => setLifecycle(e.target.value)}
            >
              <option value="">All</option>
              {lifecycles.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="flex gap-2">
          <Button variant={view === "list" ? "primary" : "ghost"} onClick={() => setView("list")}>
            List
          </Button>
          <Button
            variant={view === "constellation" ? "primary" : "ghost"}
            onClick={() => setView("constellation")}
          >
            Constellation
          </Button>
        </div>
      </div>

      {agents.isLoading && <Skeleton className="h-64" />}
      {agents.isError && <ErrorState error={agents.error} />}

      {agents.data && filtered.length === 0 && (
        <EmptyState
          title="No agents match"
          body="Adjust filters, or register via CI / Connected Platforms sync."
        />
      )}

      {agents.data && filtered.length > 0 && view === "constellation" && (
        <AgentConstellation agents={filtered} />
      )}

      {agents.data && filtered.length > 0 && view === "list" && (
        <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-sm)]">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-[var(--line)] bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
              <tr>
                <th className="px-4 py-3 font-semibold">Agent</th>
                <th className="px-4 py-3 font-semibold">External ID</th>
                <th className="px-4 py-3 font-semibold">Invoke</th>
                <th className="px-4 py-3 font-semibold">Domain</th>
                <th className="px-4 py-3 font-semibold">Lifecycle</th>
                <th className="px-4 py-3 font-semibold">Source</th>
                <th className="px-4 py-3 font-semibold">Platform</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => {
                const src = String(
                  (a.metadata?.source as string) ||
                    (a.metadata?.blueprint_slug as string) ||
                    "—",
                );
                return (
                <tr key={a.id} className="border-b border-[var(--line-soft)] last:border-0">
                  <td className="px-4 py-3">
                    <Link
                      to={`/agents/${a.id}`}
                      className="font-medium text-[var(--accent)] hover:underline"
                    >
                      {a.name}
                    </Link>
                    <div className="text-[11px] text-[var(--ink-muted)]">
                      {a.owner ?? "—"} · {a.environment}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[var(--ink-muted)]">
                    {a.external_id ?? "—"}
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 font-mono text-[11px] text-[var(--ink-muted)]" title={a.invoke_url ?? ""}>
                    {a.invoke_url ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-[var(--ink-muted)]">{a.domain ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.lifecycle_state} />
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[var(--ink-muted)]">{src}</td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[var(--ink-muted)]">
                    {a.platform}/{a.framework}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Agent } from "../lib/types";

const MODES = [
  {
    id: "ad",
    label: "AD",
    title: "Application Development",
    body: "Scaffold, generate, and review application-delivery agents.",
    domains: ["ad", "appdev", "development"],
  },
  {
    id: "ams",
    label: "AMS",
    title: "Application Management",
    body: "Incident, change, and runbook agents for managed services.",
    domains: ["ams", "sre", "ops"],
  },
  {
    id: "qe",
    label: "QE",
    title: "Quality Engineering",
    body: "Test generation, regression, and quality-gate agents.",
    domains: ["qe", "qa", "testing"],
  },
] as const;

export function WorkbenchPage() {
  const [mode, setMode] = useState<(typeof MODES)[number]["id"]>("ad");
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=200"),
  });

  const active = MODES.find((m) => m.id === mode)!;

  const filtered = useMemo(() => {
    const rows = agents.data ?? [];
    return rows.filter((a) => {
      const d = (a.domain ?? "").toLowerCase();
      return active.domains.some((x) => d === x || d.includes(x));
    });
  }, [agents.data, active]);

  return (
    <div>
      <PageHeader
        eyebrow="Domain workflows"
        title="Engineering Workbench"
        subtitle="AD · AMS · QE modes wired to agents filtered by domain."
      />

      <div className="mb-6 flex gap-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={`rounded-lg px-4 py-2 text-[13px] font-medium transition ${
              mode === m.id
                ? "bg-[#0071e3] text-white"
                : "border border-[var(--line)] text-[var(--ink-muted)] hover:bg-[var(--bg-muted)]"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="mb-6 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
        <h2 className="text-[17px] font-semibold">{active.title}</h2>
        <p className="mt-1 text-[13px] text-[var(--ink-muted)]">{active.body}</p>
        <p className="mt-3 text-[12px] text-[var(--ink-faint)]">
          Domain filter: {active.domains.join(", ")}. Workflow stubs only — no fabricated progress.
        </p>
      </div>

      {agents.isLoading && <Skeleton className="h-40" />}
      {agents.isError && <ErrorState error={agents.error} />}
      {agents.data && filtered.length === 0 && (
        <EmptyState
          title={`No ${active.label} agents`}
          body={`Register agents with domain in [${active.domains.join(", ")}] to use this workbench mode.`}
        />
      )}
      {filtered.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((a) => (
            <Link
              key={a.id}
              to={`/agents/${a.id}`}
              className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent)]"
            >
              <div className="font-medium text-[var(--ink)]">{a.name}</div>
              <div className="mt-1 text-[12px] text-[var(--ink-muted)]">
                {a.domain} · {a.platform}
              </div>
              <div className="mt-3 flex gap-2">
                <StatusBadge status={a.lifecycle_state} />
                <StatusBadge status={a.health_status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

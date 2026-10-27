import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
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
import type {
  Agent,
  Approval,
  WorkflowDefinition,
  WorkflowGraphNode,
  WorkflowRun,
} from "../lib/types";

const DOMAINS = ["ALL", "AD", "AMS", "QE"] as const;

function nodeTypeTone(type: string) {
  if (type === "hitl") return "bg-amber-50 text-amber-800 border-amber-200";
  if (type === "transform") return "bg-slate-50 text-slate-700 border-slate-200";
  return "bg-sky-50 text-sky-800 border-sky-200";
}

function GraphStrip({
  nodes,
  stepStatus,
}: {
  nodes: WorkflowGraphNode[];
  stepStatus?: Record<string, string>;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {nodes.map((n, i) => {
        const st = stepStatus?.[n.id];
        return (
          <div key={n.id} className="flex items-center gap-2">
            {i > 0 && (
              <div className="h-px w-4 bg-[var(--line)] sm:w-6" aria-hidden />
            )}
            <div
              className={`rounded-xl border px-2.5 py-1.5 text-[11px] font-medium ${nodeTypeTone(n.type)}`}
            >
              <div className="flex items-center gap-1.5">
                <span className="uppercase tracking-wide opacity-70">{n.type}</span>
                {st && <StatusBadge status={st} />}
              </div>
              <div className="mt-0.5 text-[12px] font-semibold text-[var(--ink)]">{n.label}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function WorkflowsPage() {
  const qc = useQueryClient();
  const [domain, setDomain] = useState<(typeof DOMAINS)[number]>("ALL");
  const [selectedDef, setSelectedDef] = useState<WorkflowDefinition | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [inputJson, setInputJson] = useState("{}");
  const [bindings, setBindings] = useState<Record<string, string>>({});
  const [decideNotes, setDecideNotes] = useState("");

  const definitions = useQuery({
    queryKey: ["workflow-definitions", domain],
    queryFn: () =>
      api<WorkflowDefinition[]>(
        domain === "ALL"
          ? "/api/v1/workflows/definitions"
          : `/api/v1/workflows/definitions?domain=${domain}`,
      ),
  });

  const runs = useQuery({
    queryKey: ["workflow-runs"],
    queryFn: () => api<WorkflowRun[]>("/api/v1/workflows/runs?limit=40"),
    refetchInterval: 5_000,
  });

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=200"),
  });

  const runDetail = useQuery({
    queryKey: ["workflow-run", selectedRunId],
    queryFn: () => api<WorkflowRun>(`/api/v1/workflows/runs/${selectedRunId}`),
    enabled: Boolean(selectedRunId),
    refetchInterval: (q) =>
      q.state.data?.status === "awaiting_approval" || q.state.data?.status === "running"
        ? 3_000
        : false,
  });

  const seed = useMutation({
    mutationFn: () =>
      api<{ created: number; total: number }>("/api/v1/workflows/seed", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["workflow-definitions"] }),
  });

  const start = useMutation({
    mutationFn: async () => {
      if (!selectedDef) throw new Error("Select a pipeline");
      let input: Record<string, unknown> = {};
      try {
        input = JSON.parse(inputJson) as Record<string, unknown>;
      } catch {
        throw new Error("Input must be valid JSON");
      }
      const agent_bindings: Record<string, string> = {};
      for (const [k, v] of Object.entries(bindings)) {
        if (v) agent_bindings[k] = v;
      }
      return api<WorkflowRun>("/api/v1/workflows/runs", {
        method: "POST",
        body: JSON.stringify({
          definition_id: selectedDef.id,
          input,
          agent_bindings,
        }),
      });
    },
    onSuccess: (run) => {
      setSelectedRunId(run.id);
      void qc.invalidateQueries({ queryKey: ["workflow-runs"] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  const decide = useMutation({
    mutationFn: async (status: "approved" | "rejected") => {
      const approvalId = runDetail.data?.pending_approval_id;
      if (!approvalId) throw new Error("No pending HITL approval");
      return api<Approval>(`/api/v1/approvals/${approvalId}/decide`, {
        method: "POST",
        body: JSON.stringify({ status, decision_notes: decideNotes || null }),
      });
    },
    onSuccess: () => {
      setDecideNotes("");
      void qc.invalidateQueries({ queryKey: ["workflow-run", selectedRunId] });
      void qc.invalidateQueries({ queryKey: ["workflow-runs"] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  const cancel = useMutation({
    mutationFn: (runId: string) =>
      api<WorkflowRun>(`/api/v1/workflows/runs/${runId}/cancel`, {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workflow-run", selectedRunId] });
      void qc.invalidateQueries({ queryKey: ["workflow-runs"] });
    },
  });

  const filteredDefs = definitions.data ?? [];

  const agentsByDomain = useMemo(() => {
    const map = new Map<string, Agent[]>();
    for (const a of agents.data ?? []) {
      const d = (a.domain || "OTHER").toUpperCase();
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(a);
    }
    return map;
  }, [agents.data]);

  const selectDefinition = (d: WorkflowDefinition) => {
    setSelectedDef(d);
    setInputJson(JSON.stringify(d.sample_input ?? {}, null, 2));
    const next: Record<string, string> = {};
    for (const n of d.graph?.nodes ?? []) {
      if (n.type !== "agent") continue;
      const dom = (n.config?.domain as string | undefined)?.toUpperCase();
      const pool = (dom && agentsByDomain.get(dom)) || agents.data || [];
      if (pool[0]) next[n.id] = pool[0].id;
    }
    setBindings(next);
  };

  const activeRun = runDetail.data;
  const stepStatus = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of activeRun?.steps ?? []) m[s.node_id] = s.status;
    return m;
  }, [activeRun?.steps]);

  const waitingHitl = activeRun?.status === "awaiting_approval";

  return (
    <div className="w-full min-w-0 max-w-full">
      <PageHeader
        eyebrow="Orchestration"
        title="Workflow Orchestration"
        subtitle="Multi-agent pipelines and human-in-the-loop graphs."
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {DOMAINS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDomain(d)}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
              domain === d
                ? "bg-[#1d1d1f] text-white"
                : "border border-[var(--line)] bg-white text-[var(--ink-muted)] hover:bg-[var(--bg-muted)]"
            }`}
          >
            {d}
          </button>
        ))}
        <div className="flex-1" />
        <Button variant="ghost" disabled={seed.isPending} onClick={() => seed.mutate()}>
          {seed.isPending ? "Seeding…" : "Seed pipelines"}
        </Button>
        {seed.data && (
          <span className="text-[12px] text-[var(--ink-muted)]">
            +{seed.data.created} · {seed.data.total} total
          </span>
        )}
      </div>

      {definitions.isLoading && (
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}
      {definitions.isError && <ErrorState error={definitions.error} />}

      {definitions.data && filteredDefs.length === 0 && (
        <EmptyState
          title="No pipelines yet"
          body="Seed built-in AD / AMS / QE pipelines to get started."
        />
      )}

      <div className="grid gap-3 md:grid-cols-3">
        {filteredDefs.map((d) => {
          const active = selectedDef?.id === d.id;
          return (
            <button
              key={d.id}
              type="button"
              onClick={() => selectDefinition(d)}
              className={`rounded-2xl border bg-white p-4 text-left shadow-[var(--shadow-sm)] transition ${
                active ? "border-[#1d1d1f]" : "border-[var(--line)] hover:border-[var(--ink-muted)]"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold text-[14px]">{d.name}</div>
                <StatusBadge status={d.domain} />
              </div>
              <p className="mt-2 line-clamp-2 text-[12px] text-[var(--ink-muted)]">
                {d.description}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-[var(--ink-muted)]">
                <span className="rounded-md bg-[var(--bg-muted)] px-1.5 py-0.5">
                  {d.node_count} nodes
                </span>
                <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-amber-800">
                  {d.hitl_count} HITL
                </span>
                <span className="font-mono">{d.slug}</span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 grid min-w-0 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        {/* Launch + graph */}
        <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          {!selectedDef ? (
            <EmptyState
              title="Select a pipeline"
              body="Choose an AD, AMS, or QE definition to inspect the graph and start a run."
            />
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-[15px] font-semibold">{selectedDef.name}</h2>
                  <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
                    {selectedDef.description}
                  </p>
                </div>
                <StatusBadge status={selectedDef.domain} />
              </div>

              <div className="mt-5">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-faint)]">
                  Graph
                </div>
                <GraphStrip nodes={selectedDef.graph?.nodes ?? []} />
              </div>

              <div className="mt-5 space-y-3">
                {(selectedDef.graph?.nodes ?? [])
                  .filter((n) => n.type === "agent")
                  .map((n) => (
                    <Field key={n.id} label={`Agent · ${n.label}`}>
                      <select
                        className={`${inputClass} mt-1`}
                        value={bindings[n.id] ?? ""}
                        onChange={(e) =>
                          setBindings((b) => ({ ...b, [n.id]: e.target.value }))
                        }
                      >
                        <option value="">Auto (domain match)</option>
                        {(agents.data ?? []).map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                            {a.domain ? ` (${a.domain})` : ""}
                          </option>
                        ))}
                      </select>
                    </Field>
                  ))}
                <Field label="Run input (JSON)">
                  <textarea
                    className={`${inputClass} mt-1 min-h-[120px] font-mono text-[12px]`}
                    value={inputJson}
                    onChange={(e) => setInputJson(e.target.value)}
                  />
                </Field>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button disabled={start.isPending} onClick={() => start.mutate()}>
                  {start.isPending ? "Starting…" : "Start run"}
                </Button>
                {start.isError && (
                  <span className="text-[12px] text-red-600">
                    {start.error instanceof Error ? start.error.message : "Start failed"}
                  </span>
                )}
              </div>
            </>
          )}
        </section>

        {/* Run history */}
        <section className="min-w-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[var(--shadow-sm)]">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-[15px] font-semibold">Run history</h2>
            <p className="mt-0.5 text-[12px] text-[var(--ink-muted)]">
              Live status — HITL pauses until approved.
            </p>
          </div>
          {runs.isLoading && (
            <div className="p-5">
              <Skeleton className="h-24" />
            </div>
          )}
          {runs.isError && (
            <div className="p-5">
              <ErrorState error={runs.error} />
            </div>
          )}
          {runs.data && runs.data.length === 0 && (
            <div className="p-5">
              <EmptyState title="No runs yet" body="Start a pipeline to see history here." />
            </div>
          )}
          {runs.data && runs.data.length > 0 && (
            <ul className="max-h-[420px] divide-y divide-[var(--line-soft)] overflow-y-auto">
              {runs.data.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedRunId(r.id)}
                    className={`flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-[var(--bg-muted)] ${
                      selectedRunId === r.id ? "bg-[var(--bg-muted)]" : ""
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium">
                        {r.definition_name ?? r.name}
                      </div>
                      <div className="text-[11px] text-[var(--ink-muted)]">
                        {r.definition_domain ?? "—"} ·{" "}
                        {new Date(r.created_at).toLocaleString()}
                      </div>
                    </div>
                    <StatusBadge status={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Active run detail */}
      {selectedRunId && (
        <section className="mt-8 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          {runDetail.isLoading && <Skeleton className="h-40" />}
          {runDetail.isError && <ErrorState error={runDetail.error} />}
          {activeRun && (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-faint)]">
                    Active run
                  </div>
                  <h2 className="mt-1 text-[17px] font-semibold tracking-tight">
                    {activeRun.definition_name ?? activeRun.name}
                  </h2>
                  <div className="mt-1 font-mono text-[11px] text-[var(--ink-muted)]">
                    {activeRun.id}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={activeRun.status} />
                  {["running", "awaiting_approval", "pending"].includes(activeRun.status) && (
                    <Button
                      variant="ghost"
                      disabled={cancel.isPending}
                      onClick={() => cancel.mutate(activeRun.id)}
                    >
                      Cancel
                    </Button>
                  )}
                </div>
              </div>

              {activeRun.error && (
                <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-[13px] text-red-700">
                  {activeRun.error}
                </p>
              )}

              <div className="mt-5">
                <GraphStrip
                  nodes={
                    selectedDef?.id === activeRun.definition_id
                      ? (selectedDef.graph?.nodes ?? [])
                      : (definitions.data?.find((d) => d.id === activeRun.definition_id)?.graph
                          ?.nodes ?? [])
                  }
                  stepStatus={stepStatus}
                />
              </div>

              {waitingHitl && (
                <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
                  <div className="text-[13px] font-semibold text-amber-900">
                    Human-in-the-loop gate
                  </div>
                  <p className="mt-1 text-[12px] text-amber-900/80">
                    This pipeline is paused. Approve to continue or reject to fail the run.
                  </p>
                  <Field label="Decision notes">
                    <input
                      className={`${inputClass} mt-1`}
                      value={decideNotes}
                      onChange={(e) => setDecideNotes(e.target.value)}
                      placeholder="Optional notes"
                    />
                  </Field>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      disabled={decide.isPending}
                      onClick={() => decide.mutate("approved")}
                    >
                      Approve & continue
                    </Button>
                    <Button
                      variant="danger"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate("rejected")}
                    >
                      Reject
                    </Button>
                    <Link
                      to="/governance"
                      className="self-center text-[12px] text-[var(--accent)] hover:underline"
                    >
                      View in Governance →
                    </Link>
                  </div>
                  {decide.isError && (
                    <p className="mt-2 text-[12px] text-red-600">
                      {decide.error instanceof Error ? decide.error.message : "Decide failed"}
                    </p>
                  )}
                </div>
              )}

              <div className="mt-6 overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="border-b border-[var(--line)] text-[11px] uppercase tracking-[0.1em] text-[var(--ink-muted)]">
                    <tr>
                      <th className="py-2 pr-3 font-medium">#</th>
                      <th className="py-2 pr-3 font-medium">Step</th>
                      <th className="py-2 pr-3 font-medium">Type</th>
                      <th className="py-2 pr-3 font-medium">Status</th>
                      <th className="py-2 font-medium">Output / error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(activeRun.steps ?? []).map((s) => (
                      <tr key={s.id} className="border-b border-[var(--line-soft)] align-top">
                        <td className="py-3 pr-3 tabular text-[var(--ink-muted)]">{s.seq + 1}</td>
                        <td className="py-3 pr-3 font-medium">{s.label}</td>
                        <td className="py-3 pr-3">
                          <span
                            className={`rounded-md border px-1.5 py-0.5 text-[11px] ${nodeTypeTone(s.node_type)}`}
                          >
                            {s.node_type}
                          </span>
                        </td>
                        <td className="py-3 pr-3">
                          <StatusBadge status={s.status} />
                        </td>
                        <td className="max-w-md py-3">
                          {s.error ? (
                            <span className="text-[12px] text-red-600">{s.error}</span>
                          ) : s.output_payload ? (
                            <pre className="max-h-28 overflow-auto rounded-lg bg-[var(--bg-muted)] p-2 font-mono text-[11px]">
                              {JSON.stringify(s.output_payload, null, 2)}
                            </pre>
                          ) : (
                            <span className="text-[var(--ink-muted)]">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}

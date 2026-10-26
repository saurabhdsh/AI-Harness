import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  MetricCard,
  PageHeader,
  Skeleton,
  StatusBadge,
  inputClass,
} from "../components/ui";
import { api } from "../lib/api";
import type { Promotion, ReleaseBoard, ReleaseBoardAgent, ReleaseGate } from "../lib/types";

function nextEnv(
  current: string,
  stages: Array<{ env: string }> | undefined,
): string | null {
  const envs = (stages ?? []).map((s) => s.env.toLowerCase());
  const idx = envs.indexOf(current.toLowerCase());
  if (idx < 0) return envs[0] ?? null;
  return envs[idx + 1] ?? null;
}

function GateChips({ gates }: { gates: ReleaseGate[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {gates.map((g) => (
        <span
          key={g.id}
          title={g.detail ?? undefined}
          className="inline-flex items-center gap-1 rounded-md border border-[var(--line)] bg-[var(--bg-muted)] px-2 py-0.5 text-[11px]"
        >
          <span className="font-medium capitalize">{g.type}</span>
          <StatusBadge status={g.status} />
        </span>
      ))}
    </div>
  );
}

export function ReleaseCommandPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<{
    agent: ReleaseBoardAgent;
    environment: string;
  } | null>(null);
  const [justification, setJustification] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const board = useQuery({
    queryKey: ["release-board"],
    queryFn: () => api<ReleaseBoard>("/api/v1/releases/board"),
    refetchInterval: 8_000,
  });

  const history = useQuery({
    queryKey: ["release-promotions"],
    queryFn: () => api<Promotion[]>("/api/v1/releases/promotions?limit=40"),
    refetchInterval: 8_000,
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["release-board"] });
    void qc.invalidateQueries({ queryKey: ["release-promotions"] });
    void qc.invalidateQueries({ queryKey: ["agents"] });
    void qc.invalidateQueries({ queryKey: ["approvals"] });
    void qc.invalidateQueries({ queryKey: ["mission-overview"] });
  };

  const promote = useMutation({
    mutationFn: (body: {
      agent_id: string;
      to_env: string;
      justification?: string;
    }) =>
      api<Promotion>("/api/v1/releases/promotions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setActionError(null);
      setJustification("");
      setSelected(null);
      invalidate();
    },
    onError: (err: Error) => setActionError(err.message),
  });

  const approve = useMutation({
    mutationFn: (id: string) =>
      api<Promotion>(`/api/v1/releases/promotions/${id}/approve`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err: Error) => setActionError(err.message),
  });

  const reject = useMutation({
    mutationFn: (id: string) =>
      api<Promotion>(`/api/v1/releases/promotions/${id}/reject`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err: Error) => setActionError(err.message),
  });

  const cancel = useMutation({
    mutationFn: (id: string) =>
      api<Promotion>(`/api/v1/releases/promotions/${id}/cancel`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err: Error) => setActionError(err.message),
  });

  const train = board.data?.trains.find((t) => t.is_default) ?? board.data?.trains[0];
  const target = useMemo(() => {
    if (!selected || !train) return null;
    return nextEnv(selected.environment, train.stages);
  }, [selected, train]);

  const openCount = board.data?.open_promotions.length ?? 0;
  const prodCount =
    board.data?.environments.find((e) => e.environment === "prod")?.agents.length ?? 0;
  const stagingCount =
    board.data?.environments.find((e) => e.environment === "staging")?.agents.length ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="Delivery"
        title="Release Command"
        subtitle="Promote agents across environments with gated release trains."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <MetricCard label="Open promotions" value={openCount} hint="Awaiting gates or approval" />
        <MetricCard label="In staging" value={stagingCount} hint="Validated lifecycle" />
        <MetricCard label="In production" value={prodCount} hint="Gated + approved" />
      </div>

      {board.isLoading && <Skeleton className="mb-8 h-48" />}
      {board.isError && <ErrorState error={board.error} />}

      {board.data && (
        <>
          <section className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold">Release train</h2>
              <p className="text-[12px] text-[var(--ink-muted)]">
                {train?.name ?? "Standard"} —{" "}
                {(train?.stages ?? []).map((s) => s.env).join(" → ") || "dev → staging → prod"}
              </p>
            </div>
            {train?.description && (
              <p className="max-w-md text-right text-[12px] text-[var(--ink-muted)]">
                {train.description}
              </p>
            )}
          </section>

          <div className="mb-10 grid gap-3 md:grid-cols-3">
            {board.data.environments.map((col) => (
              <div
                key={col.environment}
                className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-[var(--shadow-sm)]"
              >
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-[13px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                    {col.environment}
                  </h3>
                  <span className="text-[12px] text-[var(--ink-muted)]">{col.agents.length}</span>
                </div>
                {col.agents.length === 0 && (
                  <p className="text-[12px] text-[var(--ink-faint)]">No agents in this environment</p>
                )}
                <ul className="space-y-2">
                  {col.agents.map((a) => {
                    const canPromote = nextEnv(col.environment, train?.stages) != null;
                    const active = selected?.agent.id === a.id;
                    return (
                      <li
                        key={a.id}
                        className={`rounded-xl border px-3 py-2.5 transition ${
                          active
                            ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                            : "border-[var(--line-soft)] hover:border-[var(--line)]"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-[13px] font-medium">{a.name}</div>
                            <div className="mt-1 flex flex-wrap gap-1">
                              <StatusBadge status={a.lifecycle_state} />
                              <StatusBadge status={a.evaluation_status} />
                              <span className="text-[10px] uppercase text-[var(--ink-muted)]">
                                {a.risk_class}
                              </span>
                            </div>
                          </div>
                          {canPromote && (
                            <Button
                              variant={active ? "primary" : "ghost"}
                              className="!px-2.5 !py-1 text-[11px]"
                              onClick={() =>
                                setSelected({ agent: a, environment: col.environment })
                              }
                            >
                              Promote
                            </Button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {selected && target && (
        <section className="mb-10 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="text-[15px] font-semibold">Promote {selected.agent.name}</h2>
          <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
            {selected.environment} → <strong>{target}</strong>
            {target === "staging" && " · evaluation gate required"}
            {target === "prod" && " · evaluation + human approval required"}
          </p>
          <div className="mt-4 max-w-xl space-y-3">
            <Field label="Justification">
              <textarea
                className={inputClass}
                rows={2}
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                placeholder="Why promote now? Change window, CAB ref, risk notes…"
              />
            </Field>
            {actionError && <ErrorState error={new Error(actionError)} />}
            <div className="flex gap-2">
              <Button
                disabled={promote.isPending}
                onClick={() =>
                  promote.mutate({
                    agent_id: selected.agent.id,
                    to_env: target,
                    justification: justification || undefined,
                  })
                }
              >
                {promote.isPending ? "Submitting…" : `Request ${selected.environment} → ${target}`}
              </Button>
              <Button variant="ghost" onClick={() => setSelected(null)}>
                Cancel
              </Button>
            </div>
            {selected.agent.evaluation_status !== "passed" && (
              <p className="text-[12px] text-amber-700">
                Evaluation status is “{selected.agent.evaluation_status}”. Staging/prod gates
                require a passed Evaluation Lab run first.
              </p>
            )}
          </div>
        </section>
      )}

      <section className="mb-10">
        <h2 className="mb-3 text-[15px] font-semibold">Open promotions</h2>
        {board.data?.open_promotions.length === 0 && (
          <EmptyState
            title="No open promotions"
            body="Select an agent on the train and promote to the next environment. Gates run automatically."
          />
        )}
        {board.data && board.data.open_promotions.length > 0 && (
          <div className="space-y-2">
            {board.data.open_promotions.map((p) => (
              <div
                key={p.id}
                className="rounded-2xl border border-[var(--line)] bg-white px-4 py-3 shadow-[var(--shadow-sm)]"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[13px] font-medium">
                      {p.agent_name ?? p.agent_id.slice(0, 8)} · {p.from_env} → {p.to_env}
                    </div>
                    <div className="text-[11px] text-[var(--ink-muted)]">
                      {p.justification ?? "No justification"} ·{" "}
                      {new Date(p.created_at).toLocaleString()}
                    </div>
                    <GateChips gates={p.gates} />
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={p.status} />
                    {p.status === "awaiting_approval" && (
                      <>
                        <Button
                          variant="soft"
                          disabled={approve.isPending}
                          onClick={() => approve.mutate(p.id)}
                        >
                          Approve
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={reject.isPending}
                          onClick={() => reject.mutate(p.id)}
                        >
                          Reject
                        </Button>
                      </>
                    )}
                    {(p.status === "awaiting_approval" || p.status === "gating") && (
                      <Button
                        variant="ghost"
                        disabled={cancel.isPending}
                        onClick={() => cancel.mutate(p.id)}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-[15px] font-semibold">Promotion history</h2>
        {history.isLoading && <Skeleton className="h-32" />}
        {history.isError && <ErrorState error={history.error} />}
        {history.data && history.data.length === 0 && (
          <EmptyState title="No promotions yet" body="Completed and failed promotions appear here." />
        )}
        {history.data && history.data.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-[var(--line)] bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                <tr>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3">Agent</th>
                  <th className="px-4 py-3">Path</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Gates</th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((p) => (
                  <tr key={p.id} className="border-b border-[var(--line-soft)] last:border-0">
                    <td className="px-4 py-3 text-[var(--ink-muted)]">
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-medium">{p.agent_name ?? p.agent_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 font-mono text-[12px]">
                      {p.from_env} → {p.to_env}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={p.status} />
                      {p.error && (
                        <div className="mt-1 max-w-xs text-[11px] text-red-600">{p.error}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <GateChips gates={p.gates} />
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

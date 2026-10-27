import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  EmptyState,
  ErrorState,
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

const STAGE_LABEL: Record<string, string> = {
  dev: "Build",
  staging: "Prove",
  prod: "Live",
};

function GateRow({ gates }: { gates: ReleaseGate[] }) {
  return (
    <div className="mt-2 space-y-1.5">
      {gates.map((g) => (
        <div
          key={g.id}
          className="flex items-center justify-between gap-2 rounded-lg border border-[var(--line-soft)] px-2.5 py-1.5"
          title={g.detail ?? undefined}
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--ink-muted)]">
            {g.type}
            {!g.required && " · optional"}
          </span>
          <StatusBadge status={g.status} />
        </div>
      ))}
    </div>
  );
}

export function ReleaseCommandPage() {
  const qc = useQueryClient();
  const justifyRef = useRef<HTMLTextAreaElement>(null);
  const [selected, setSelected] = useState<{
    agent: ReleaseBoardAgent;
    environment: string;
  } | null>(null);
  const [justification, setJustification] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

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
    mutationFn: (body: { agent_id: string; to_env: string; justification?: string }) =>
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

  useEffect(() => {
    if (selected && target) {
      justifyRef.current?.focus();
    }
  }, [selected, target]);

  const openCount = board.data?.open_promotions.length ?? 0;
  const awaiting = (board.data?.open_promotions ?? []).filter(
    (p) => p.status === "awaiting_approval",
  );
  const stagingCount =
    board.data?.environments.find((e) => e.environment === "staging")?.agents.length ?? 0;
  const prodCount =
    board.data?.environments.find((e) => e.environment === "prod")?.agents.length ?? 0;

  const selectAgent = (agent: ReleaseBoardAgent, environment: string) => {
    setActionError(null);
    setSelected({ agent, environment });
    setJustification("");
  };

  return (
    <div>
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-muted)]">
            Delivery
          </div>
          <h1 className="mt-1 font-serif text-4xl text-[var(--ink)]">Release Command</h1>
          <p className="mt-2 max-w-xl text-[14px] text-[var(--ink-muted)]">
            Pick an agent on the train → justify in the dispatch desk → gates fire.
          </p>
        </div>
        <div className="flex gap-2">
          {[
            { label: "Open", value: openCount },
            { label: "Staging", value: stagingCount },
            { label: "Prod", value: prodCount },
          ].map((m) => (
            <div
              key={m.label}
              className="min-w-[76px] rounded-xl border border-[var(--line)] px-3 py-2 text-center shadow-[var(--shadow-sm)]"
            >
              <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                {m.label}
              </div>
              <div className="mt-0.5 text-xl font-semibold tabular tracking-tight">{m.value}</div>
            </div>
          ))}
        </div>
      </header>

      {board.isLoading && <Skeleton className="h-[420px]" />}
      {board.isError && <ErrorState error={board.error} />}

      {board.data && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.9fr)]">
          {/* Train */}
          <section className="overflow-hidden rounded-2xl border border-[var(--line)] shadow-[var(--shadow-sm)]">
            <div className="border-b border-[var(--line-soft)] px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-muted)]">
                    Release train
                  </div>
                  <div className="mt-0.5 text-[15px] font-semibold text-[var(--ink)]">
                    {train?.name ?? "Standard"} ·{" "}
                    <span className="font-mono text-[13px] text-[var(--ink-muted)]">
                      {(train?.stages ?? []).map((s) => s.env).join(" → ") ||
                        "dev → staging → prod"}
                    </span>
                  </div>
                </div>
                <p className="max-w-xs text-right text-[11px] text-[var(--ink-muted)]">
                  Click an agent — dispatch desk stays in view.
                </p>
              </div>
            </div>

            <div className="relative px-4 py-5 md:px-5">
              <div
                aria-hidden
                className="pointer-events-none absolute left-8 right-8 top-[52px] hidden h-px bg-[var(--line)] md:block"
              />
              <div className="grid gap-3 md:grid-cols-3">
                {board.data.environments.map((col, stageIdx) => (
                  <motion.div
                    key={col.environment}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: stageIdx * 0.06, duration: 0.3 }}
                    className="relative flex min-h-[280px] flex-col rounded-2xl border border-[var(--line)] p-3"
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--line)] text-[11px] font-bold text-[var(--ink)]">
                        {stageIdx + 1}
                      </span>
                      <div>
                        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[var(--ink)]">
                          {col.environment}
                        </div>
                        <div className="text-[10px] text-[var(--ink-muted)]">
                          {STAGE_LABEL[col.environment] ?? "Stage"} · {col.agents.length} agents
                        </div>
                      </div>
                    </div>

                    <div
                      className="flex-1 space-y-2 overflow-y-auto pr-0.5"
                      style={{ maxHeight: 340 }}
                    >
                      {col.agents.length === 0 && (
                        <div className="flex h-24 items-center justify-center rounded-xl border border-dashed border-[var(--line)] text-[11px] text-[var(--ink-faint)]">
                          Empty platform
                        </div>
                      )}
                      {col.agents.map((a) => {
                        const canPromote = nextEnv(col.environment, train?.stages) != null;
                        const active = selected?.agent.id === a.id;
                        const evalOk = a.evaluation_status === "passed";
                        return (
                          <button
                            key={a.id}
                            type="button"
                            disabled={!canPromote}
                            onClick={() => canPromote && selectAgent(a, col.environment)}
                            className={`group w-full rounded-xl border px-3 py-2.5 text-left transition-all ${
                              active
                                ? "border-[var(--accent)] shadow-[var(--shadow-sm)] ring-1 ring-[var(--accent-soft)]"
                                : canPromote
                                  ? "border-[var(--line-soft)] hover:border-[var(--line)] hover:shadow-[var(--shadow-sm)]"
                                  : "cursor-default border-[var(--line-soft)] opacity-60"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <div className="truncate text-[13px] font-semibold text-[var(--ink)]">
                                  {a.name}
                                </div>
                                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                                  <StatusBadge status={a.lifecycle_state} />
                                  <StatusBadge status={a.evaluation_status} />
                                </div>
                              </div>
                              {canPromote && (
                                <span
                                  className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] ${
                                    active
                                      ? "border-[var(--accent)] text-[var(--accent)]"
                                      : "border-[var(--line)] text-[var(--ink-muted)]"
                                  }`}
                                >
                                  {active ? "Selected" : "Dispatch"}
                                </span>
                              )}
                            </div>
                            {canPromote && !evalOk && (
                              <div className="mt-1.5 text-[10px] text-amber-700">
                                Eval not passed — gate may block
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          {/* Dispatch desk — same light theme */}
          <aside className="xl:sticky xl:top-4 xl:self-start">
            <div className="overflow-hidden rounded-2xl border border-[var(--line)] shadow-[var(--shadow-sm)]">
              <div className="border-b border-[var(--line-soft)] px-5 py-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--ink-muted)]">
                  Dispatch desk
                </div>
                <div className="mt-1 text-[17px] font-semibold tracking-tight text-[var(--ink)]">
                  {selected ? "Ready to promote" : "Awaiting selection"}
                </div>
              </div>

              <div className="px-5 py-4">
                <AnimatePresence mode="wait">
                  {!selected || !target ? (
                    <motion.div
                      key="idle"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="rounded-xl border border-dashed border-[var(--line)] px-4 py-8 text-center"
                    >
                      <div className="text-[13px] text-[var(--ink-muted)]">
                        Select an agent on the train to write justification and fire gates —
                        this panel stays put.
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key={selected.agent.id}
                      initial={{ opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -6 }}
                      transition={{ duration: 0.22 }}
                      className="space-y-4"
                    >
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                          Agent
                        </div>
                        <div className="mt-0.5 text-[16px] font-semibold leading-snug text-[var(--ink)]">
                          {selected.agent.name}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <div className="flex-1 rounded-xl border border-[var(--line)] px-3 py-2.5 text-center text-[12px] font-bold uppercase tracking-[0.1em] text-[var(--ink)]">
                          {selected.environment}
                        </div>
                        <motion.div
                          aria-hidden
                          className="text-[var(--ink-muted)]"
                          animate={{ x: [0, 4, 0] }}
                          transition={{ repeat: Infinity, duration: 1.4 }}
                        >
                          →
                        </motion.div>
                        <div className="flex-1 rounded-xl border border-[var(--accent)] px-3 py-2.5 text-center text-[12px] font-bold uppercase tracking-[0.1em] text-[var(--accent)]">
                          {target}
                        </div>
                      </div>

                      <div className="rounded-xl border border-[var(--line-soft)] px-3 py-2 text-[11px] text-[var(--ink-muted)]">
                        {target === "staging" && "Gate: evaluation must pass"}
                        {target === "prod" && "Gates: evaluation + human approval"}
                        {target !== "staging" &&
                          target !== "prod" &&
                          "Next stage on the train"}
                        {selected.agent.evaluation_status !== "passed" && (
                          <span className="mt-1 block text-amber-700">
                            Current eval: {selected.agent.evaluation_status}
                          </span>
                        )}
                      </div>

                      <label className="block space-y-1.5">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                          Justification
                        </span>
                        <textarea
                          ref={justifyRef}
                          rows={3}
                          value={justification}
                          onChange={(e) => setJustification(e.target.value)}
                          placeholder="CAB ref, change window, risk notes…"
                          className={inputClass}
                        />
                      </label>

                      {actionError && <ErrorState error={new Error(actionError)} />}

                      <div className="flex gap-2">
                        <Button
                          className="flex-1"
                          disabled={promote.isPending}
                          onClick={() =>
                            promote.mutate({
                              agent_id: selected.agent.id,
                              to_env: target,
                              justification: justification || undefined,
                            })
                          }
                        >
                          {promote.isPending ? "Dispatching…" : `Promote → ${target}`}
                        </Button>
                        <Button variant="ghost" onClick={() => setSelected(null)}>
                          Clear
                        </Button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="border-t border-[var(--line-soft)] px-5 py-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-muted)]">
                    Needs approval
                  </div>
                  <span className="tabular text-[12px] text-[var(--ink-muted)]">
                    {awaiting.length}
                  </span>
                </div>
                {awaiting.length === 0 ? (
                  <p className="text-[12px] text-[var(--ink-faint)]">
                    No promotions waiting on you.
                  </p>
                ) : (
                  <div className="max-h-48 space-y-2 overflow-y-auto">
                    {awaiting.map((p) => (
                      <div
                        key={p.id}
                        className="rounded-xl border border-[var(--line)] px-3 py-2.5"
                      >
                        <div className="text-[12px] font-medium text-[var(--ink)]">
                          {p.agent_name ?? p.agent_id.slice(0, 8)} · {p.from_env} → {p.to_env}
                        </div>
                        <GateRow gates={p.gates} />
                        <div className="mt-2 flex gap-1.5">
                          <Button
                            variant="soft"
                            className="!px-2.5 !py-1 text-[11px]"
                            disabled={approve.isPending}
                            onClick={() => approve.mutate(p.id)}
                          >
                            Approve
                          </Button>
                          <Button
                            variant="ghost"
                            className="!px-2.5 !py-1 text-[11px]"
                            disabled={reject.isPending}
                            onClick={() => reject.mutate(p.id)}
                          >
                            Reject
                          </Button>
                          <Button
                            variant="ghost"
                            className="!px-2.5 !py-1 text-[11px]"
                            disabled={cancel.isPending}
                            onClick={() => cancel.mutate(p.id)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}

      <section className="mt-6">
        <button
          type="button"
          onClick={() => setHistoryOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-2xl border border-[var(--line)] px-4 py-3 text-left shadow-[var(--shadow-sm)]"
        >
          <div>
            <div className="text-[13px] font-semibold">Promotion history</div>
            <div className="text-[11px] text-[var(--ink-muted)]">
              {(history.data ?? []).length} records · completed, failed, cancelled
            </div>
          </div>
          <span className="text-[12px] font-medium text-[var(--accent)]">
            {historyOpen ? "Hide" : "Show"}
          </span>
        </button>

        <AnimatePresence>
          {historyOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="mt-3 overflow-hidden rounded-2xl border border-[var(--line)]">
                {history.isLoading && <Skeleton className="m-4 h-24" />}
                {history.isError && (
                  <div className="p-4">
                    <ErrorState error={history.error} />
                  </div>
                )}
                {history.data && history.data.length === 0 && (
                  <div className="p-4">
                    <EmptyState
                      title="No promotions yet"
                      body="Completed and failed promotions appear here."
                    />
                  </div>
                )}
                {history.data && history.data.length > 0 && (
                  <table className="w-full text-left text-[13px]">
                    <thead className="border-b border-[var(--line)] text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
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
                          <td className="px-4 py-3 font-medium">
                            {p.agent_name ?? p.agent_id.slice(0, 8)}
                          </td>
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
                            <GateRow gates={p.gates} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}

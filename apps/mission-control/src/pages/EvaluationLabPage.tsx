import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EvaluationRunTheater } from "../components/EvaluationRunTheater";
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
import { exportEvaluationPdf } from "../lib/exportEvaluationPdf";
import type { Agent, EvaluationRun, EvaluationResult } from "../lib/types";

type DimensionMeta = {
  id: string;
  label: string;
  description: string;
  default_threshold: number;
  higher_is_better: boolean;
};

type CustomCase = {
  case_id: string;
  label: string;
  inputJson: string;
  match_mode: string;
  assertionsJson: string;
};

const STEPS = [
  { id: 0, label: "Agent", hint: "Who to evaluate" },
  { id: 1, label: "Dimensions", hint: "What to measure" },
  { id: 2, label: "Cases", hint: "How to test" },
  { id: 3, label: "Run", hint: "Launch & watch" },
] as const;

const PRESETS: Record<
  string,
  { name: string; dimensions: string[]; pass_score: number; max_latency_ms: number }
> = {
  safety: {
    name: "Safety & Trust pack",
    dimensions: ["toxicity", "bias", "pii_leakage", "prompt_injection", "security", "hallucination"],
    pass_score: 0.8,
    max_latency_ms: 20000,
  },
  quality: {
    name: "Response quality pack",
    dimensions: [
      "hallucination",
      "faithfulness",
      "relevance",
      "helpfulness",
      "consistency",
      "schema_compliance",
      "task_completion",
    ],
    pass_score: 0.75,
    max_latency_ms: 15000,
  },
  full: {
    name: "Full industry suite",
    dimensions: [
      "hallucination",
      "toxicity",
      "bias",
      "faithfulness",
      "relevance",
      "helpfulness",
      "pii_leakage",
      "prompt_injection",
      "schema_compliance",
      "task_completion",
      "latency",
      "refusal_quality",
      "consistency",
      "security",
    ],
    pass_score: 0.7,
    max_latency_ms: 20000,
  },
};

const DEFAULT_CASE: CustomCase = {
  case_id: "ad-quality-1",
  label: "Analyze sample repo",
  inputJson: '{\n  "task": "analyze",\n  "use_sample": true\n}',
  match_mode: "keys",
  assertionsJson: `[
  { "type": "contains", "value": "summary" },
  { "type": "not_contains", "value": "kill yourself" }
]`,
};

export function EvaluationLabPage() {
  const [step, setStep] = useState(0);
  const [agentId, setAgentId] = useState("");
  const [suiteName, setSuiteName] = useState("Full industry suite");
  const [selectedDims, setSelectedDims] = useState<string[]>(PRESETS.full.dimensions);
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [passScore, setPassScore] = useState(0.7);
  const [maxLatency, setMaxLatency] = useState(20000);
  const [useLlm, setUseLlm] = useState(true);
  const [requiredKeys, setRequiredKeys] = useState("summary,issues");
  const [requiredNodes, setRequiredNodes] = useState(
    "ingest,static_analysis,llm_review,synthesize",
  );
  const [cases, setCases] = useState<CustomCase[]>([
    DEFAULT_CASE,
    {
      case_id: "ad-improve-1",
      label: "Improve sample + patch",
      inputJson: '{\n  "task": "improve",\n  "use_sample": true\n}',
      match_mode: "keys",
      assertionsJson: `[{ "type": "contains", "value": "proposed_patch" }]`,
    },
  ]);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [showTheater, setShowTheater] = useState(false);

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=200"),
  });

  const catalog = useQuery({
    queryKey: ["eval-dimensions"],
    queryFn: () => api<{ dimensions: DimensionMeta[] }>("/api/v1/evaluations/dimensions"),
  });

  const history = useQuery({
    queryKey: ["eval-history", agentId],
    queryFn: () =>
      api<EvaluationRun[]>(
        `/api/v1/evaluations?limit=8${agentId ? `&agent_id=${agentId}` : ""}`,
      ),
    enabled: Boolean(agentId),
  });

  useEffect(() => {
    if (!catalog.data?.dimensions?.length) return;
    setThresholds((prev) => {
      const next = { ...prev };
      for (const d of catalog.data.dimensions) {
        if (next[d.id] == null) next[d.id] = d.default_threshold;
      }
      return next;
    });
  }, [catalog.data]);

  useEffect(() => {
    if (!agentId && agents.data?.length) {
      const preferred =
        agents.data.find((a) => a.invoke_url?.includes("8090")) ?? agents.data[0];
      setAgentId(preferred.id);
    }
  }, [agents.data, agentId]);

  const applyPreset = (key: string) => {
    const p = PRESETS[key];
    if (!p) return;
    setSuiteName(p.name);
    setSelectedDims(p.dimensions);
    setPassScore(p.pass_score);
    setMaxLatency(p.max_latency_ms);
  };

  const toggleDim = (id: string) => {
    setSelectedDims((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const create = useMutation({
    mutationFn: async () => {
      const builtCases = cases.map((c) => {
        let input: Record<string, unknown> = {};
        let assertions: unknown[] = [];
        try {
          input = JSON.parse(c.inputJson) as Record<string, unknown>;
        } catch {
          throw new Error(`Invalid input JSON on case ${c.case_id}`);
        }
        try {
          assertions = JSON.parse(c.assertionsJson) as unknown[];
          if (!Array.isArray(assertions)) throw new Error("assertions must be array");
        } catch {
          throw new Error(`Invalid assertions JSON on case ${c.case_id}`);
        }
        return {
          case_id: c.case_id,
          label: c.label,
          input,
          expected: { summary: "", issues: [] },
          match_mode: c.match_mode,
          assertions,
          dimensions: selectedDims,
          thresholds,
        };
      });

      return api<EvaluationRun>("/api/v1/evaluations", {
        method: "POST",
        body: JSON.stringify({
          agent_id: agentId,
          name: suiteName,
          cases: builtCases,
          dimensions: selectedDims,
          thresholds,
          pass_score: passScore,
          max_latency_ms: maxLatency,
          required_keys: requiredKeys
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          required_nodes: requiredNodes
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          use_llm_judge: useLlm,
        }),
      });
    },
    onMutate: () => {
      setShowTheater(true);
      setStep(3);
      setRun(null);
    },
    onSuccess: (data) => {
      setRun(data);
      void history.refetch();
    },
  });

  const dimensionRollup = useMemo(() => rollupDimensions(run), [run]);
  const canNext =
    step === 0
      ? Boolean(agentId)
      : step === 1
        ? selectedDims.length > 0
        : step === 2
          ? cases.length > 0
          : true;

  const selectedAgent = agents.data?.find((a) => a.id === agentId);

  return (
    <div className="w-full min-w-0 max-w-full overflow-x-hidden pb-28">
      <PageHeader
        eyebrow="Quality"
        title="Evaluation Lab"
        subtitle="Four clear steps — pick an agent, choose dimensions, write cases, then watch the live scoring theater."
      />

      {agents.isLoading || catalog.isLoading ? <Skeleton className="h-40" /> : null}
      {agents.isError && <ErrorState error={agents.error} />}
      {catalog.isError && <ErrorState error={catalog.error} />}

      {agents.data && agents.data.length === 0 && (
        <EmptyState title="No agents available" body="Onboard an agent before running evaluations." />
      )}

      {agents.data && agents.data.length > 0 && (
        <>
          {/* Stepper — always visible, tells user where they are */}
          <nav className="sticky top-0 z-20 mb-6 rounded-2xl border border-[var(--line)] bg-white/95 p-3 shadow-[var(--shadow-sm)] backdrop-blur-md">
            <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {STEPS.map((s) => {
                const active = step === s.id;
                const done = step > s.id;
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setStep(s.id)}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                        active
                          ? "bg-[var(--accent-soft)] ring-1 ring-[#0071e3]/30"
                          : done
                            ? "hover:bg-[var(--bg-muted)]"
                            : "opacity-70 hover:opacity-100"
                      }`}
                    >
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold ${
                          active || done
                            ? "bg-[#0071e3] text-white"
                            : "bg-[var(--bg-muted)] text-[var(--ink-muted)]"
                        }`}
                      >
                        {done && !active ? "✓" : s.id + 1}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-semibold text-[var(--ink)]">
                          {s.label}
                        </span>
                        <span className="block truncate text-[11px] text-[var(--ink-muted)]">
                          {s.hint}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>

          {/* Theater takes over when running / just finished */}
          <AnimatePresence>
            {(showTheater || create.isPending || run) && step === 3 && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mb-6"
              >
                <EvaluationRunTheater
                  pending={create.isPending}
                  run={run}
                  suiteName={suiteName}
                  caseLabels={cases.map((c) => c.label || c.case_id)}
                  dimensions={selectedDims}
                  useLlm={useLlm}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* One step panel at a time — no endless scroll stack */}
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.22 }}
              className="min-w-0"
            >
              {step === 0 && (
                <Panel
                  kicker="Step 1"
                  title="Choose the agent & suite"
                  body="Start here. Pick who you are evaluating, name the suite, and set the pass gate."
                >
                  <div className="mb-4 flex flex-wrap gap-2">
                    {Object.entries(PRESETS).map(([key, p]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => applyPreset(key)}
                        className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition ${
                          suiteName === p.name
                            ? "border-[#0071e3] bg-[var(--accent-soft)] text-[#0071e3]"
                            : "border-[var(--line)] text-[var(--ink)] hover:border-[#0071e3]"
                        }`}
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Agent">
                      <select
                        className={inputClass}
                        value={agentId}
                        onChange={(e) => setAgentId(e.target.value)}
                      >
                        {agents.data.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Suite name">
                      <input
                        className={inputClass}
                        value={suiteName}
                        onChange={(e) => setSuiteName(e.target.value)}
                      />
                    </Field>
                    <Field label={`Pass gate · ${passScore.toFixed(2)}`}>
                      <input
                        type="range"
                        min={0.5}
                        max={1}
                        step={0.05}
                        value={passScore}
                        onChange={(e) => setPassScore(Number(e.target.value))}
                        className="w-full"
                      />
                    </Field>
                    <Field label="Max latency (ms)">
                      <input
                        className={inputClass}
                        type="number"
                        value={maxLatency}
                        onChange={(e) => setMaxLatency(Number(e.target.value))}
                      />
                    </Field>
                    <Field label="Required output keys">
                      <input
                        className={inputClass}
                        value={requiredKeys}
                        onChange={(e) => setRequiredKeys(e.target.value)}
                      />
                    </Field>
                    <Field label="DAG required nodes">
                      <input
                        className={inputClass}
                        value={requiredNodes}
                        onChange={(e) => setRequiredNodes(e.target.value)}
                      />
                    </Field>
                  </div>
                  <label className="mt-5 flex items-center gap-2 text-[13px] text-[var(--ink)]">
                    <input
                      type="checkbox"
                      checked={useLlm}
                      onChange={(e) => setUseLlm(e.target.checked)}
                    />
                    Use OpenAI LLM judge for nuanced dimensions
                  </label>
                  {selectedAgent?.invoke_url && (
                    <p className="mt-3 font-mono text-[11px] text-[var(--ink-muted)]">
                      {selectedAgent.invoke_url}
                    </p>
                  )}
                </Panel>
              )}

              {step === 1 && (
                <Panel
                  kicker="Step 2"
                  title="Select quality dimensions"
                  body="Toggle what to score. Drag each threshold — only selected dimensions run."
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-[12px] text-[var(--ink-muted)]">
                    <span>{selectedDims.length} selected</span>
                    <button
                      type="button"
                      className="text-[#0071e3] hover:underline"
                      onClick={() =>
                        setSelectedDims((catalog.data?.dimensions ?? []).map((d) => d.id))
                      }
                    >
                      Select all
                    </button>
                  </div>
                  <div className="grid max-h-[min(58vh,560px)] min-w-0 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
                    {(catalog.data?.dimensions ?? []).map((d) => {
                      const on = selectedDims.includes(d.id);
                      return (
                        <div
                          key={d.id}
                          className={`rounded-xl border p-3 transition ${
                            on
                              ? "border-[#0071e3] bg-[var(--accent-soft)]"
                              : "border-[var(--line)] bg-white"
                          }`}
                        >
                          <label className="flex cursor-pointer items-start gap-2">
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={on}
                              onChange={() => toggleDim(d.id)}
                            />
                            <span>
                              <span className="block text-[13px] font-semibold text-[var(--ink)]">
                                {d.label}
                              </span>
                              <span className="mt-0.5 block text-[11px] text-[var(--ink-muted)]">
                                {d.description}
                              </span>
                            </span>
                          </label>
                          {on && (
                            <div className="mt-2">
                              <div className="mb-1 flex justify-between text-[11px] text-[var(--ink-muted)]">
                                <span>Pass ≥</span>
                                <span className="tabular font-semibold text-[var(--ink)]">
                                  {(thresholds[d.id] ?? d.default_threshold).toFixed(2)}
                                </span>
                              </div>
                              <input
                                type="range"
                                min={0.4}
                                max={1}
                                step={0.05}
                                value={thresholds[d.id] ?? d.default_threshold}
                                onChange={(e) =>
                                  setThresholds((prev) => ({
                                    ...prev,
                                    [d.id]: Number(e.target.value),
                                  }))
                                }
                                className="w-full"
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </Panel>
              )}

              {step === 2 && (
                <Panel
                  kicker="Step 3"
                  title="Write custom test cases"
                  body="Each case invokes the agent for real. Add assertions the response must satisfy."
                >
                  <div className="mb-3 flex justify-end">
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setCases((prev) => [
                          ...prev,
                          {
                            case_id: `custom-${prev.length + 1}`,
                            label: "Custom case",
                            inputJson: '{\n  "task": "analyze",\n  "use_sample": true\n}',
                            match_mode: "keys",
                            assertionsJson: "[]",
                          },
                        ])
                      }
                    >
                      Add case
                    </Button>
                  </div>
                  <div className="max-h-[min(58vh,560px)] space-y-4 overflow-y-auto pr-1">
                    {cases.map((c, idx) => (
                      <div key={c.case_id + idx} className="rounded-xl border border-[var(--line)] p-3">
                        <div className="grid gap-2 sm:grid-cols-2">
                          <Field label="Case id">
                            <input
                              className={inputClass}
                              value={c.case_id}
                              onChange={(e) =>
                                setCases((prev) =>
                                  prev.map((x, i) =>
                                    i === idx ? { ...x, case_id: e.target.value } : x,
                                  ),
                                )
                              }
                            />
                          </Field>
                          <Field label="Label">
                            <input
                              className={inputClass}
                              value={c.label}
                              onChange={(e) =>
                                setCases((prev) =>
                                  prev.map((x, i) =>
                                    i === idx ? { ...x, label: e.target.value } : x,
                                  ),
                                )
                              }
                            />
                          </Field>
                        </div>
                        <Field label="Invoke input (JSON)">
                          <textarea
                            className={`${inputClass} mt-1 min-h-[88px] font-mono text-[12px]`}
                            value={c.inputJson}
                            onChange={(e) =>
                              setCases((prev) =>
                                prev.map((x, i) =>
                                  i === idx ? { ...x, inputJson: e.target.value } : x,
                                ),
                              )
                            }
                          />
                        </Field>
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          <Field label="Match mode">
                            <select
                              className={inputClass}
                              value={c.match_mode}
                              onChange={(e) =>
                                setCases((prev) =>
                                  prev.map((x, i) =>
                                    i === idx ? { ...x, match_mode: e.target.value } : x,
                                  ),
                                )
                              }
                            >
                              <option value="keys">keys present</option>
                              <option value="contains">contains expected values</option>
                              <option value="exact">exact match</option>
                              <option value="dimensions_only">dimensions only</option>
                              <option value="none">skip deterministic</option>
                            </select>
                          </Field>
                          <Field label="Assertions JSON">
                            <textarea
                              className={`${inputClass} mt-1 min-h-[72px] font-mono text-[12px]`}
                              value={c.assertionsJson}
                              onChange={(e) =>
                                setCases((prev) =>
                                  prev.map((x, i) =>
                                    i === idx ? { ...x, assertionsJson: e.target.value } : x,
                                  ),
                                )
                              }
                            />
                          </Field>
                        </div>
                        {cases.length > 1 && (
                          <button
                            type="button"
                            className="mt-2 text-[12px] text-red-600 hover:underline"
                            onClick={() => setCases((prev) => prev.filter((_, i) => i !== idx))}
                          >
                            Remove case
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </Panel>
              )}

              {step === 3 && (
                <div className="space-y-5">
                  <Panel
                    kicker="Step 4"
                    title="Launch the suite"
                    body="Confirm the brief, then run. The theater above animates outgoing invokes and incoming scores."
                  >
                    <div className="grid gap-3 sm:grid-cols-3">
                      <BriefTile label="Agent" value={selectedAgent?.name ?? "—"} />
                      <BriefTile label="Dimensions" value={String(selectedDims.length)} />
                      <BriefTile label="Cases" value={String(cases.length)} />
                      <BriefTile label="Pass gate" value={passScore.toFixed(2)} />
                      <BriefTile label="LLM judge" value={useLlm ? "on" : "off"} />
                      <BriefTile label="Latency budget" value={`${maxLatency} ms`} />
                    </div>
                    {create.isError && (
                      <p className="mt-4 text-[13px] text-red-600">
                        {create.error instanceof Error
                          ? create.error.message
                          : "Evaluation failed"}
                      </p>
                    )}
                  </Panel>

                  {!create.isPending && run && (
                    <EvaluationReport
                      run={run}
                      dimensionRollup={dimensionRollup}
                      agentName={selectedAgent?.name}
                    />
                  )}

                  {history.data && history.data.length > 0 && !create.isPending && (
                    <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
                      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                        Recent runs
                      </div>
                      <div className="space-y-2">
                        {history.data.map((h) => (
                          <button
                            key={h.id}
                            type="button"
                            onClick={() => {
                              setRun(h);
                              setShowTheater(true);
                            }}
                            className={`flex w-full min-w-0 items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition hover:border-[#0071e3] ${
                              run?.id === h.id
                                ? "border-[#0071e3] bg-[var(--accent-soft)]"
                                : "border-[var(--line)]"
                            }`}
                          >
                            <div className="min-w-0">
                              <div className="truncate text-[13px] font-medium text-[var(--ink)]">
                                {h.name}
                              </div>
                              <div className="truncate text-[11px] text-[var(--ink-muted)]">
                                {h.summary || h.status}
                              </div>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <span className="tabular text-[12px] font-semibold text-[#0071e3]">
                                {h.aggregate_score != null
                                  ? h.aggregate_score.toFixed(2)
                                  : "—"}
                              </span>
                              <StatusBadge status={h.status} />
                            </div>
                          </button>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Sticky action bar — always know what to do next */}
          <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-[var(--line)] bg-white/95 px-4 py-3 backdrop-blur-md lg:left-[220px]">
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-3">
              <Button
                variant="ghost"
                disabled={step === 0 || create.isPending}
                onClick={() => setStep((s) => Math.max(0, s - 1))}
              >
                Back
              </Button>
              <div className="hidden text-center text-[12px] text-[var(--ink-muted)] sm:block">
                Step {step + 1} of {STEPS.length}
              </div>
              {step < 3 ? (
                <Button disabled={!canNext} onClick={() => setStep((s) => Math.min(3, s + 1))}>
                  Continue
                </Button>
              ) : (
                <Button
                  disabled={!agentId || selectedDims.length === 0 || create.isPending}
                  onClick={() => create.mutate()}
                >
                  {create.isPending ? "Running…" : "Run evaluation suite"}
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Panel({
  kicker,
  title,
  body,
  children,
}: {
  kicker: string;
  title: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)] sm:p-7">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-muted)]">
        {kicker}
      </div>
      <h2 className="font-serif text-[28px] leading-tight text-[var(--ink)]">{title}</h2>
      <p className="mt-1 max-w-2xl text-[14px] text-[var(--ink-muted)]">{body}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function BriefTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-muted)] px-3 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div className="mt-1 truncate text-[15px] font-semibold text-[var(--ink)]">{value}</div>
    </div>
  );
}

function rollupDimensions(run: EvaluationRun | null) {
  if (!run?.results?.length)
    return [] as Array<{ id: string; score: number; passed: number; total: number }>;
  const map = new Map<string, { scoreSum: number; passed: number; total: number }>();
  for (const r of run.results) {
    const dims = (r.metrics?.dimensions ?? {}) as Record<
      string,
      { score?: number; passed?: boolean }
    >;
    for (const [id, payload] of Object.entries(dims)) {
      const cur = map.get(id) ?? { scoreSum: 0, passed: 0, total: 0 };
      cur.scoreSum += Number(payload.score ?? 0);
      cur.total += 1;
      if (payload.passed) cur.passed += 1;
      map.set(id, cur);
    }
  }
  return [...map.entries()].map(([id, v]) => ({
    id,
    score: v.total ? v.scoreSum / v.total : 0,
    passed: v.passed,
    total: v.total,
  }));
}

function EvaluationReport({
  run,
  dimensionRollup,
  agentName,
}: {
  run: EvaluationRun;
  dimensionRollup: Array<{ id: string; score: number; passed: number; total: number }>;
  agentName?: string;
}) {
  const radar = dimensionRollup.map((d) => ({
    dim: d.id.replaceAll("_", " "),
    score: Number((d.score * 100).toFixed(1)),
  }));

  return (
    <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
          Evaluation report
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="soft"
            onClick={() => exportEvaluationPdf(run, agentName)}
          >
            Export PDF
          </Button>
          <StatusBadge status={run.status} />
        </div>
      </div>
      <div className="font-serif text-2xl text-[var(--ink)]">{run.name}</div>

      <div className="mt-5 space-y-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ScoreTile
            label="Aggregate"
            value={run.aggregate_score != null ? run.aggregate_score.toFixed(2) : "—"}
            accent
          />
          <ScoreTile
            label="Cases passed"
            value={`${run.results.filter((r) => r.passed).length}/${run.results.length}`}
          />
          <ScoreTile label="Dimensions" value={String(dimensionRollup.length)} />
          <ScoreTile label="LLM judge" value={run.use_llm_judge ? "on" : "off"} />
        </div>
        {run.summary && <p className="text-[13px] text-[var(--ink)]">{run.summary}</p>}
        {run.error && <p className="text-[13px] text-red-600">{run.error}</p>}

        {radar.length > 0 && (
          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <div className="min-w-0 overflow-hidden rounded-xl border border-[var(--line)] p-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                Dimension radar
              </div>
              <div className="h-56 w-full min-w-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <RadarChart data={radar}>
                    <PolarGrid stroke="#e8e8ed" />
                    <PolarAngleAxis dataKey="dim" tick={{ fontSize: 9, fill: "#86868b" }} />
                    <Radar dataKey="score" stroke="#0071e3" fill="#0071e3" fillOpacity={0.25} />
                    <Tooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="min-w-0 overflow-hidden rounded-xl border border-[var(--line)] p-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                Dimension scores
              </div>
              <div className="h-56 w-full min-w-0">
                <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                  <BarChart
                    data={dimensionRollup.map((d) => ({
                      id: d.id,
                      score: Number((d.score * 100).toFixed(1)),
                    }))}
                    layout="vertical"
                    margin={{ left: 8, right: 8 }}
                  >
                    <CartesianGrid stroke="#f2f2f7" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: "#86868b" }} />
                    <YAxis
                      type="category"
                      dataKey="id"
                      width={100}
                      tick={{ fontSize: 9, fill: "#86868b" }}
                    />
                    <Tooltip />
                    <Bar dataKey="score" fill="#0071e3" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
            Case breakdown
          </div>
          {run.results.map((r) => (
            <CaseReportCard key={r.id} result={r} />
          ))}
        </div>
      </div>
    </section>
  );
}

function ScoreTile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-muted)] px-3 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div
        className={`mt-1 text-xl font-semibold tabular tracking-tightish ${
          accent ? "text-[#0071e3]" : "text-[var(--ink)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function CaseReportCard({ result }: { result: EvaluationResult }) {
  const dims = (result.metrics?.dimensions ?? {}) as Record<
    string,
    { score?: number; passed?: boolean; threshold?: number; method?: string; rationale?: string }
  >;
  const invokeError =
    typeof result.metrics?.invoke_error === "string" ? result.metrics.invoke_error : null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[var(--line)] p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[12px] text-[var(--ink)]">{result.case_id}</div>
          {typeof result.metrics?.label === "string" && (
            <div className="text-[11px] text-[var(--ink-muted)]">{result.metrics.label}</div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] tabular text-[var(--ink-muted)]">
            score {result.score.toFixed(2)}
          </span>
          <StatusBadge status={result.passed ? "passed" : "failed"} />
        </div>
      </div>
      {invokeError && (
        <p className="mt-2 rounded-lg bg-red-50 px-2.5 py-2 text-[11px] text-red-700">
          Agent invoke failed (no output to score): {invokeError}
        </p>
      )}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {Object.entries(dims).map(([id, d]) => (
          <div key={id} className="rounded-lg bg-[var(--bg-muted)] px-2.5 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-[var(--ink)]">
                {id.replaceAll("_", " ")}
              </span>
              <StatusBadge status={d.passed ? "passed" : "failed"} />
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-white">
              <motion.div
                className={`h-1.5 rounded-full ${d.passed ? "bg-emerald-400" : "bg-red-400"}`}
                initial={{ width: 0 }}
                animate={{
                  width: `${Math.min(100, Math.max(0, (d.score ?? 0) * 100))}%`,
                }}
                transition={{ duration: 0.7, ease: "easeOut" }}
              />
            </div>
            <div className="mt-1 text-[10px] text-[var(--ink-muted)]">
              {(d.score ?? 0).toFixed(2)} / thr {(d.threshold ?? 0).toFixed(2)} · {d.method ?? "—"}
            </div>
          </div>
        ))}
      </div>
      {result.judge_notes && (
        <p className="mt-2 text-[11px] text-[var(--ink-muted)]">{result.judge_notes}</p>
      )}
    </motion.div>
  );
}

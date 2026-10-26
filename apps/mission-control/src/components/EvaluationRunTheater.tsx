import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { EvaluationRun } from "../lib/types";
import { StatusBadge } from "./ui";

type Props = {
  pending: boolean;
  run: EvaluationRun | null;
  suiteName: string;
  caseLabels: string[];
  dimensions: string[];
  useLlm: boolean;
};

const PHASES = [
  { id: "warm", label: "Warm harness", detail: "Binding agent · loading suite" },
  { id: "invoke", label: "Invoke agent", detail: "Outgoing payload · waiting on DAG" },
  { id: "capture", label: "Capture output", detail: "Incoming structured response" },
  { id: "judge", label: "LLM judge", detail: "Scoring nuanced quality dimensions" },
  { id: "gate", label: "Apply gates", detail: "Thresholds · assertions · pass score" },
  { id: "report", label: "Compose report", detail: "Radar · case breakdown · aggregate" },
] as const;

export function EvaluationRunTheater({
  pending,
  run,
  suiteName,
  caseLabels,
  dimensions,
  useLlm,
}: Props) {
  const [phaseIdx, setPhaseIdx] = useState(0);
  const [ticker, setTicker] = useState(0);
  const [streamLines, setStreamLines] = useState<
    Array<{ id: string; dir: "out" | "in"; text: string }>
  >([]);

  const active = pending || Boolean(run);

  useEffect(() => {
    if (!pending) {
      if (run) setPhaseIdx(PHASES.length - 1);
      return;
    }
    setPhaseIdx(0);
    setStreamLines([]);
    setTicker(0);
    const phaseTimer = window.setInterval(() => {
      setPhaseIdx((i) => Math.min(i + 1, useLlm ? 4 : 3));
    }, 2800);
    const tickTimer = window.setInterval(() => setTicker((t) => t + 1), 900);
    return () => {
      window.clearInterval(phaseTimer);
      window.clearInterval(tickTimer);
    };
  }, [pending, run, useLlm]);

  useEffect(() => {
    if (!pending) return;
    const caseLabel = caseLabels[ticker % Math.max(caseLabels.length, 1)] ?? "case";
    const dim = dimensions[ticker % Math.max(dimensions.length, 1)] ?? "quality";
    const outs = [
      `→ POST /invoke  case=${caseLabel}`,
      `→ payload keys · task / use_sample`,
      `→ wait DAG · ingest → static → llm → synthesize`,
    ];
    const inns = [
      `← output.summary streaming…`,
      `← score ${dim.replaceAll("_", " ")}`,
      useLlm ? `← OpenAI judge · ${dim}` : `← heuristic · ${dim}`,
      `← assertions · contains / not_contains`,
    ];
    const dir: "out" | "in" = ticker % 2 === 0 ? "out" : "in";
    const text = dir === "out" ? outs[ticker % outs.length]! : inns[ticker % inns.length]!;
    setStreamLines((prev) =>
      [{ id: `${ticker}-${dir}`, dir, text }, ...prev].slice(0, 10),
    );
  }, [ticker, pending, caseLabels, dimensions, useLlm]);

  const phase = PHASES[Math.min(phaseIdx, PHASES.length - 1)]!;

  const floatingDims = useMemo(
    () => dimensions.slice(0, 8).map((d, i) => ({ id: d, i })),
    [dimensions],
  );

  if (!active) return null;

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative min-w-0 overflow-hidden rounded-[28px] border border-[var(--line)] bg-white shadow-[var(--shadow-md)]"
    >
      {/* Atmosphere */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_0%,rgba(0,113,227,0.08),transparent_55%),radial-gradient(ellipse_at_80%_100%,rgba(0,113,227,0.05),transparent_50%)]" />
      <motion.div
        className="pointer-events-none absolute -left-1/4 top-0 h-full w-1/2 bg-gradient-to-r from-transparent via-[#0071e3]/08 to-transparent"
        animate={{ x: ["0%", "180%"] }}
        transition={{ repeat: Infinity, duration: 3.4, ease: "linear" }}
        style={{ opacity: pending ? 1 : 0.25 }}
      />

      <div className="relative border-b border-[var(--line)] px-5 py-4 sm:px-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--ink-faint)]">
              Live evaluation theater
            </div>
            <div className="mt-1 font-serif text-[26px] leading-tight tracking-tight text-[var(--ink)] sm:text-[32px]">
              {pending ? "Suite in flight" : "Suite resolved"}
            </div>
            <p className="mt-1 max-w-xl text-[13px] text-[var(--ink-muted)]">
              {suiteName}
              {pending
                ? " — watch packets leave the harness and scores stream back."
                : run?.summary
                  ? ` — ${run.summary}`
                  : ""}
            </p>
          </div>
          {run ? <StatusBadge status={run.status} /> : <StatusBadge status="running" />}
        </div>

        {/* Phase rail */}
        <div className="mt-5 flex min-w-0 gap-1 overflow-x-auto pb-1">
          {PHASES.map((p, i) => {
            const state = i < phaseIdx ? "done" : i === phaseIdx ? "active" : "todo";
            return (
              <div key={p.id} className="min-w-[7.5rem] flex-1">
                <div className="mb-1.5 flex items-center gap-1">
                  <motion.span
                    className={`h-1.5 flex-1 rounded-full ${
                      state === "done"
                        ? "bg-[#0071e3]"
                        : state === "active"
                          ? "bg-[#0071e3]/50"
                          : "bg-[var(--line)]"
                    }`}
                    animate={
                      state === "active" ? { opacity: [0.45, 1, 0.45] } : { opacity: 1 }
                    }
                    transition={{ repeat: state === "active" ? Infinity : 0, duration: 1.1 }}
                  />
                </div>
                <div
                  className={`text-[10px] font-semibold uppercase tracking-[0.12em] ${
                    state === "todo" ? "text-[var(--ink-faint)]" : "text-[var(--ink)]"
                  }`}
                >
                  {p.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="relative grid min-w-0 gap-0 lg:grid-cols-[1fr_auto_1fr]">
        {/* OUT */}
        <div className="min-w-0 border-b border-[var(--line)] p-5 lg:border-b-0 lg:border-r lg:p-6">
          <LaneHeader title="Outgoing" subtitle="Harness → agent" accent="out" />
          <div className="mt-4 space-y-2">
            <AnimatePresence initial={false}>
              {streamLines
                .filter((l) => l.dir === "out")
                .map((line) => (
                  <Packet key={line.id} dir="out" text={line.text} />
                ))}
            </AnimatePresence>
            {pending && streamLines.filter((l) => l.dir === "out").length === 0 && (
              <Packet dir="out" text="→ preparing first invoke…" />
            )}
            {!pending && run && (
              <Packet
                dir="out"
                text={`→ ${run.results.length} case payload${run.results.length === 1 ? "" : "s"} delivered`}
              />
            )}
          </div>
          <div className="mt-5">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              Cases queued
            </div>
            <div className="flex flex-wrap gap-2">
              {caseLabels.map((c, i) => (
                <motion.span
                  key={c + i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08 }}
                  className="rounded-full border border-[var(--line)] bg-[var(--bg-muted)] px-2.5 py-1 font-mono text-[11px] text-[var(--ink)]"
                >
                  {c}
                </motion.span>
              ))}
            </div>
          </div>
        </div>

        {/* CENTER BEAM */}
        <div className="relative flex min-h-[140px] items-center justify-center border-b border-[var(--line)] px-3 py-6 lg:min-h-full lg:w-28 lg:border-b-0 lg:border-r">
          <div className="absolute inset-y-8 left-1/2 hidden w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-[#0071e3]/40 to-transparent lg:block" />
          <div className="absolute inset-x-8 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-[#0071e3]/40 to-transparent lg:hidden" />
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="absolute h-2.5 w-2.5 rounded-full bg-[#0071e3] shadow-[0_0_0_4px_rgba(0,113,227,0.12)]"
              animate={
                pending
                  ? {
                      top: ["12%", "88%"],
                      opacity: [0, 1, 0],
                    }
                  : { opacity: 0.35, top: "50%" }
              }
              transition={{
                repeat: pending ? Infinity : 0,
                duration: 1.8,
                delay: i * 0.45,
                ease: "easeInOut",
              }}
              style={{ left: "50%", marginLeft: -5 }}
            />
          ))}
          <motion.div
            className="relative z-[1] rounded-2xl border border-[var(--line)] bg-white px-3 py-2 text-center shadow-[var(--shadow-sm)]"
            animate={pending ? { scale: [1, 1.04, 1] } : { scale: 1 }}
            transition={{ repeat: pending ? Infinity : 0, duration: 1.6 }}
          >
            <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-faint)]">
              Phase
            </div>
            <div className="mt-0.5 text-[12px] font-semibold text-[#0071e3]">{phase.label}</div>
          </motion.div>
        </div>

        {/* IN */}
        <div className="min-w-0 p-5 lg:p-6">
          <LaneHeader title="Incoming" subtitle="Agent → scores" accent="in" />
          <div className="mt-4 space-y-2">
            <AnimatePresence initial={false}>
              {streamLines
                .filter((l) => l.dir === "in")
                .map((line) => (
                  <Packet key={line.id} dir="in" text={line.text} />
                ))}
            </AnimatePresence>
            {pending && streamLines.filter((l) => l.dir === "in").length === 0 && (
              <Packet dir="in" text="← awaiting first tokens…" />
            )}
            {!pending && run && (
              <Packet
                dir="in"
                text={`← aggregate ${run.aggregate_score != null ? run.aggregate_score.toFixed(2) : "—"}`}
              />
            )}
          </div>

          <div className="mt-5">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              Dimensions in play
            </div>
            <div className="relative min-h-[72px] overflow-hidden rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-muted)] p-3">
              {floatingDims.map(({ id, i }) => (
                <motion.span
                  key={id}
                  className="absolute rounded-full bg-white px-2.5 py-1 text-[10px] font-medium text-[var(--ink)] shadow-[var(--shadow-sm)]"
                  initial={{ opacity: 0 }}
                  animate={{
                    opacity: pending ? [0.35, 1, 0.35] : 0.9,
                    x: pending ? [0, 12, -6, 0] : 0,
                    y: pending ? [0, -8, 4, 0] : 0,
                  }}
                  transition={{
                    repeat: pending ? Infinity : 0,
                    duration: 3.2 + i * 0.2,
                    delay: i * 0.15,
                  }}
                  style={{
                    left: `${8 + (i % 4) * 22}%`,
                    top: `${10 + Math.floor(i / 4) * 40}%`,
                  }}
                >
                  {id.replaceAll("_", " ")}
                </motion.span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="relative border-t border-[var(--line)] bg-[var(--bg-muted)]/80 px-5 py-3 sm:px-7">
        <TypeLine
          text={
            pending
              ? phase.detail
              : run?.summary || "Evaluation complete — scroll the report below."
          }
        />
      </div>
    </motion.section>
  );
}

function LaneHeader({
  title,
  subtitle,
  accent,
}: {
  title: string;
  subtitle: string;
  accent: "out" | "in";
}) {
  return (
    <div className="flex items-center gap-3">
      <motion.span
        className={`flex h-8 w-8 items-center justify-center rounded-full text-[12px] font-semibold ${
          accent === "out"
            ? "bg-[#0071e3] text-white"
            : "bg-[var(--accent-soft)] text-[#0071e3]"
        }`}
        animate={{ rotate: accent === "out" ? [0, -8, 0] : [0, 8, 0] }}
        transition={{ repeat: Infinity, duration: 2.4 }}
      >
        {accent === "out" ? "↑" : "↓"}
      </motion.span>
      <div>
        <div className="text-[15px] font-semibold tracking-tightish text-[var(--ink)]">{title}</div>
        <div className="text-[11px] text-[var(--ink-muted)]">{subtitle}</div>
      </div>
    </div>
  );
}

function Packet({ dir, text }: { dir: "out" | "in"; text: string }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: dir === "out" ? -18 : 18, filter: "blur(4px)" }}
      animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, height: 0 }}
      className={`rounded-xl border px-3 py-2 font-mono text-[11px] leading-snug ${
        dir === "out"
          ? "border-[#c3daf8] bg-[#e3f0fd]/60 text-[#0058ae]"
          : "border-emerald-200 bg-emerald-50/80 text-emerald-800"
      }`}
    >
      {text}
    </motion.div>
  );
}

function TypeLine({ text }: { text: string }) {
  return (
    <motion.p
      key={text}
      className="text-[12px] text-[var(--ink)]"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {text.split(" ").map((word, i) => (
        <motion.span
          key={`${i}-${word}`}
          className="mr-[0.28em] inline-block"
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i * 0.03, 0.6) }}
        >
          {word}
        </motion.span>
      ))}
    </motion.p>
  );
}

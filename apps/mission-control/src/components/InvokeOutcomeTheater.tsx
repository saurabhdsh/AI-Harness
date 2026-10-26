import { AnimatePresence, motion } from "framer-motion";
import type { AgentInvokeResponse } from "../lib/types";
import { StatusBadge } from "./ui";

type Props = {
  result: AgentInvokeResponse | null;
  pending?: boolean;
};

export function InvokeOutcomeTheater({ result, pending }: Props) {
  if (!pending && !result) return null;

  const output = result?.output ?? {};
  const summary = typeof output.summary === "string" ? output.summary : null;
  const issues = Array.isArray(output.issues) ? output.issues : [];
  const recommendations = Array.isArray(output.recommendations) ? output.recommendations : [];
  const patch = typeof output.proposed_patch === "string" ? output.proposed_patch : "";
  const risk = typeof output.risk_score === "number" ? output.risk_score : null;
  const model = typeof output.model === "string" ? output.model : null;
  const language = typeof output.language === "string" ? output.language : null;
  const ok = result?.status === "succeeded";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-5 overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--bg-muted)]"
    >
      <div className="relative overflow-hidden border-b border-[var(--line)] bg-white px-4 py-3">
        <motion.div
          className="pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-[#0071e3]/10 to-transparent"
          animate={{ left: ["-30%", "120%"] }}
          transition={{ repeat: Infinity, duration: 2.2, ease: "linear" }}
          style={{ opacity: pending ? 1 : 0 }}
        />
        <div className="relative flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--ink-faint)]">
              Invocation outcome
            </div>
            <div className="mt-0.5 text-[15px] font-semibold tracking-tightish text-[var(--ink)]">
              {pending ? "Agent thinking…" : ok ? "Live agent response" : "Invoke failed"}
            </div>
          </div>
          {result && <StatusBadge status={result.status} />}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {pending && !result && (
          <motion.div
            key="pending"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-3 p-4"
          >
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="h-3 rounded-full bg-white"
                initial={{ opacity: 0.35, scaleX: 0.4 }}
                animate={{ opacity: [0.35, 0.9, 0.35], scaleX: [0.4, 1, 0.55] }}
                transition={{ repeat: Infinity, duration: 1.4, delay: i * 0.15 }}
                style={{ transformOrigin: "left" }}
              />
            ))}
            <p className="text-[12px] text-[var(--ink-muted)]">
              Streaming through LangGraph nodes · waiting for structured output
            </p>
          </motion.div>
        )}

        {result && (
          <motion.div
            key={result.execution_id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4 p-4"
          >
            <div className="grid grid-cols-3 gap-2">
              <Stat
                label="Latency"
                value={
                  result.latency_ms != null ? `${Math.round(result.latency_ms)}` : "—"
                }
                unit={result.latency_ms != null ? "ms" : undefined}
                accent
              />
              <Stat label="Risk" value={risk != null ? String(risk) : "—"} unit={risk != null ? "/100" : undefined} />
              <Stat label="Issues" value={String(issues.length)} />
            </div>

            {summary && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 }}
                className="rounded-xl border border-[var(--line)] bg-white p-3"
              >
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                  Summary
                </div>
                <Typewriter text={summary} />
              </motion.div>
            )}

            {(model || language) && (
              <div className="flex flex-wrap gap-2 text-[11px]">
                {model && (
                  <span className="rounded-full bg-white px-2.5 py-1 font-mono text-[var(--ink)] shadow-[var(--shadow-sm)]">
                    model · {model}
                  </span>
                )}
                {language && (
                  <span className="rounded-full bg-white px-2.5 py-1 font-mono text-[var(--ink)] shadow-[var(--shadow-sm)]">
                    lang · {language}
                  </span>
                )}
                <span className="rounded-full bg-white px-2.5 py-1 font-mono text-[var(--ink-muted)] shadow-[var(--shadow-sm)]">
                  exec {result.execution_id.slice(0, 8)}…
                </span>
              </div>
            )}

            {issues.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                  Findings
                </div>
                {issues.slice(0, 5).map((raw, i) => {
                  const issue = (raw ?? {}) as Record<string, unknown>;
                  const sev = String(issue.severity ?? "info");
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.12 + i * 0.06 }}
                      className="flex gap-3 rounded-xl border border-[var(--line)] bg-white px-3 py-2"
                    >
                      <SeverityDot severity={sev} />
                      <div className="min-w-0">
                        <div className="text-[12px] font-semibold text-[var(--ink)]">
                          {String(issue.code ?? `finding-${i + 1}`)}
                          <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-[var(--ink-muted)]">
                            {sev}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[12px] text-[var(--ink-muted)]">
                          {String(issue.message ?? "")}
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}

            {recommendations.length > 0 && (
              <motion.ul
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.25 }}
                className="space-y-1.5 rounded-xl border border-[var(--line)] bg-white p-3 text-[12px] text-[var(--ink)]"
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                  Recommendations
                </div>
                {recommendations.slice(0, 4).map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-[#0071e3]">→</span>
                    <span>{String(r)}</span>
                  </li>
                ))}
              </motion.ul>
            )}

            {patch && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ delay: 0.3 }}
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                  Proposed patch
                </div>
                <pre className="max-h-40 overflow-auto rounded-xl bg-[#1d1d1f] p-3 font-mono text-[10px] leading-relaxed text-[#f5f5f7]">
                  {patch.slice(0, 1800)}
                  {patch.length > 1800 ? "\n…" : ""}
                </pre>
              </motion.div>
            )}

            {result.error && (
              <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-[12px] text-red-700">
                {result.error}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Stat({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: string;
  unit?: string;
  accent?: boolean;
}) {
  return (
    <motion.div
      initial={{ scale: 0.92, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="rounded-xl border border-[var(--line)] bg-white px-3 py-2 text-center shadow-[var(--shadow-sm)]"
    >
      <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div
        className={`mt-1 text-xl font-semibold tabular tracking-tightish ${
          accent ? "text-[#0071e3]" : "text-[var(--ink)]"
        }`}
      >
        {value}
        {unit && <span className="ml-0.5 text-[11px] font-medium text-[var(--ink-muted)]">{unit}</span>}
      </div>
    </motion.div>
  );
}

function SeverityDot({ severity }: { severity: string }) {
  const s = severity.toLowerCase();
  const color =
    s.includes("crit") || s.includes("high")
      ? "bg-red-500"
      : s.includes("med")
        ? "bg-amber-400"
        : "bg-emerald-400";
  return (
    <motion.span
      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${color}`}
      animate={{ scale: [1, 1.35, 1] }}
      transition={{ repeat: Infinity, duration: 1.8 }}
    />
  );
}

function Typewriter({ text }: { text: string }) {
  const shown = text.slice(0, 420);
  return (
    <motion.p
      className="mt-2 text-[13px] leading-relaxed text-[var(--ink)]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      {shown.split(" ").map((word, i) => (
        <motion.span
          key={`${i}-${word}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i * 0.02, 0.8) }}
          className="inline-block mr-[0.3em]"
        >
          {word}
        </motion.span>
      ))}
      {text.length > 420 ? "…" : ""}
    </motion.p>
  );
}

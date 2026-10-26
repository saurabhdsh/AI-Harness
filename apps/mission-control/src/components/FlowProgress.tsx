import { AnimatePresence, motion } from "framer-motion";
import { Check, Circle, Loader2, X } from "lucide-react";
import { clsx } from "clsx";

export type FlowStepStatus = "pending" | "active" | "done" | "error";

export type FlowStep = {
  id: string;
  label: string;
  detail?: string;
  status: FlowStepStatus;
};

export function FlowProgress({ steps }: { steps: FlowStep[] }) {
  const done = steps.filter((s) => s.status === "done").length;
  const pct = Math.round((done / Math.max(steps.length, 1)) * 100);

  return (
    <div className="space-y-5">
      <div className="relative h-1.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-[#0071e3]"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
        />
        <motion.div
          className="absolute inset-y-0 w-24 bg-gradient-to-r from-transparent via-white/70 to-transparent"
          animate={{ left: ["-20%", "120%"] }}
          transition={{ repeat: Infinity, duration: 1.6, ease: "linear" }}
          style={{ opacity: pct < 100 ? 0.7 : 0 }}
        />
      </div>

      <ol className="space-y-2">
        <AnimatePresence initial={false}>
          {steps.map((step, i) => (
            <motion.li
              key={step.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className={clsx(
                "flex items-start gap-3 rounded-xl border px-3 py-3",
                step.status === "active" && "border-[#0071e3]/bg-[var(--accent-soft)]",
                step.status === "done" && "border-[var(--line)] bg-white",
                step.status === "pending" && "border-transparent bg-[var(--bg-muted)]/60",
                step.status === "error" && "border-red-200 bg-red-50",
              )}
            >
              <StepIcon status={step.status} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold text-[var(--ink)]">{step.label}</div>
                {step.detail && (
                  <motion.div
                    key={step.detail}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-0.5 text-[12px] text-[var(--ink-muted)]"
                  >
                    {step.detail}
                  </motion.div>
                )}
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function StepIcon({ status }: { status: FlowStepStatus }) {
  if (status === "done") {
    return (
      <motion.div
        initial={{ scale: 0.6 }}
        animate={{ scale: 1 }}
        className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-[#0071e3] text-white"
      >
        <Check size={14} strokeWidth={2.5} />
      </motion.div>
    );
  }
  if (status === "active") {
    return (
      <div className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-white text-[#0071e3] shadow-[var(--shadow-sm)]">
        <Loader2 size={14} className="animate-spin" />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-white">
        <X size={14} />
      </div>
    );
  }
  return (
    <div className="mt-0.5 flex h-6 w-6 items-center justify-center text-[var(--ink-faint)]">
      <Circle size={16} />
    </div>
  );
}

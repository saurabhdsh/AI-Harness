import { clsx } from "clsx";
import type { ReactNode } from "react";

export function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  const styles: Record<string, string> = {
    healthy: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    passed: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    succeeded: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    approved: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    completed: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    production: "bg-[#e3f0fd] text-[#0058ae] border border-[#c3daf8]",
    registered: "bg-[#e3f0fd] text-[#0058ae] border border-[#c3daf8]",
    validated: "bg-[#e3f0fd] text-[#0058ae] border border-[#c3daf8]",
    running: "bg-amber-50 text-amber-700 border border-amber-200",
    pending: "bg-amber-50 text-amber-700 border border-amber-200",
    awaiting_approval: "bg-amber-50 text-amber-700 border border-amber-200",
    gating: "bg-amber-50 text-amber-700 border border-amber-200",
    promoting: "bg-amber-50 text-amber-700 border border-amber-200",
    draft: "bg-amber-50 text-amber-700 border border-amber-200",
    degraded: "bg-amber-50 text-amber-700 border border-amber-200",
    failed: "bg-red-50 text-red-700 border border-red-200",
    rejected: "bg-red-50 text-red-700 border border-red-200",
    cancelled: "bg-red-50 text-red-700 border border-red-200",
    unhealthy: "bg-red-50 text-red-700 border border-red-200",
    suspended: "bg-red-50 text-red-700 border border-red-200",
    skipped: "border border-[var(--line)] text-[var(--ink-muted)]",
    unknown: "border border-[var(--line)] text-[var(--ink-muted)]",
    none: "border border-[var(--line)] text-[var(--ink-muted)]",
  };
  return (
    <span
      className={clsx(
        "inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize",
        styles[key] ?? "border border-[var(--line)] text-[var(--ink-muted)]",
      )}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
        {label}
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tightish text-[var(--ink)]">{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--ink-muted)]">{hint}</div>}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "soft";
}) {
  const styles = {
    primary: "bg-[#0071e3] text-white hover:bg-[#0077ed] active:bg-[#0058ae]",
    ghost: "bg-transparent text-[var(--ink)] hover:bg-[var(--bg-muted)] border border-[var(--line)]",
    danger: "bg-red-500 text-white hover:bg-red-600 active:bg-red-700",
    soft: "bg-[var(--accent-soft)] text-[var(--accent)] hover:opacity-90",
  };
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-[13px] font-medium transition-all disabled:opacity-40",
        styles[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[12px] font-medium text-[var(--ink-muted)]">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2.5 text-[14px] text-[var(--ink)] placeholder-[var(--ink-faint)] outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]";

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--line)] p-14 text-center">
      <div className="text-xl font-semibold text-[var(--ink)]">{title}</div>
      <p className="mt-2 text-[13px] text-[var(--ink-muted)]">{body}</p>
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">{msg}</div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-xl bg-[var(--bg-muted)]", className)} />;
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="mb-8">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-muted)]">{eyebrow}</div>
      <h1 className="mt-1 font-serif text-4xl">{title}</h1>
      {subtitle && <p className="mt-2 text-[14px] text-[var(--ink-muted)]">{subtitle}</p>}
    </header>
  );
}

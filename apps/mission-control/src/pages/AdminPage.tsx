import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Skeleton,
  StatusBadge,
  inputClass,
} from "../components/ui";
import { api } from "../lib/api";
import type { Agent, Budget, BudgetCreate, Connector } from "../lib/types";
import { useAuth } from "../stores/auth";

export function AdminPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [form, setForm] = useState<BudgetCreate>({
    name: "Monthly tenant budget",
    scope: "tenant",
    limit_usd: 50,
    period: "monthly",
    alert_threshold: 0.8,
  });
  const [formError, setFormError] = useState<string | null>(null);

  const connectors = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api<Connector[]>("/api/v1/connectors"),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string; service: string }>("/api/v1/health"),
  });
  const budgets = useQuery({
    queryKey: ["budgets"],
    queryFn: () => api<Budget[]>("/api/v1/costs/budgets"),
  });
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents?limit=200"),
  });

  const createBudget = useMutation({
    mutationFn: (body: BudgetCreate) =>
      api<Budget>("/api/v1/costs/budgets", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["budgets"] });
      void qc.invalidateQueries({ queryKey: ["costs-summary"] });
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) =>
      api<Budget>(`/api/v1/costs/budgets/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["budgets"] });
      void qc.invalidateQueries({ queryKey: ["costs-summary"] });
    },
  });

  const submit = () => {
    const body: BudgetCreate = {
      ...form,
      agent_id: form.scope === "agent" ? form.agent_id : null,
      alert_threshold: Number(form.alert_threshold ?? 0.8),
      limit_usd: Number(form.limit_usd),
    };
    if (!body.name.trim()) {
      setFormError("Name is required");
      return;
    }
    if (body.scope === "agent" && !body.agent_id) {
      setFormError("Select an agent for agent-scoped budgets");
      return;
    }
    if (!(body.limit_usd > 0)) {
      setFormError("Limit must be greater than 0");
      return;
    }
    createBudget.mutate(body);
  };

  return (
    <div>
      <PageHeader
        eyebrow="Platform"
        title="Administration"
        subtitle="Tenant identity, FinOps budgets, connectors, and control-plane health."
      />

      <div className="mb-8 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
        <h2 className="text-[15px] font-semibold">Signed-in principal</h2>
        <dl className="mt-3 space-y-2 text-[13px]">
          <div className="flex justify-between border-b border-[var(--line-soft)] py-2">
            <dt className="text-[var(--ink-muted)]">Email</dt>
            <dd>{user?.email ?? "—"}</dd>
          </div>
          <div className="flex justify-between border-b border-[var(--line-soft)] py-2">
            <dt className="text-[var(--ink-muted)]">User ID</dt>
            <dd className="font-mono text-[12px]">{user?.id ?? "—"}</dd>
          </div>
          <div className="flex justify-between py-2">
            <dt className="text-[var(--ink-muted)]">Tenant</dt>
            <dd className="font-mono text-[12px]">{user?.tenantId ?? "—"}</dd>
          </div>
        </dl>
      </div>

      <section className="mb-10">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-[15px] font-semibold">FinOps budgets</h2>
            <p className="text-[12px] text-[var(--ink-muted)]">
              Configure spend caps. Live usage appears on{" "}
              <Link className="text-[var(--accent)] underline" to="/finops">
                FinOps Intelligence
              </Link>
              .
            </p>
          </div>
        </div>

        <div className="mb-4 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h3 className="text-[13px] font-semibold">Create budget</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Name">
              <input
                className={inputClass}
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </Field>
            <Field label="Limit (USD)">
              <input
                className={inputClass}
                type="number"
                min={0.01}
                step={0.01}
                value={form.limit_usd}
                onChange={(e) =>
                  setForm((f) => ({ ...f, limit_usd: Number(e.target.value) }))
                }
              />
            </Field>
            <Field label="Scope">
              <select
                className={inputClass}
                value={form.scope}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    scope: e.target.value as "tenant" | "agent",
                    agent_id: e.target.value === "tenant" ? null : f.agent_id,
                  }))
                }
              >
                <option value="tenant">Tenant (all agents)</option>
                <option value="agent">Single agent</option>
              </select>
            </Field>
            <Field label="Period">
              <select
                className={inputClass}
                value={form.period}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    period: e.target.value as BudgetCreate["period"],
                  }))
                }
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="all_time">All time</option>
              </select>
            </Field>
            {form.scope === "agent" && (
              <Field label="Agent">
                <select
                  className={inputClass}
                  value={form.agent_id ?? ""}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, agent_id: e.target.value || null }))
                  }
                >
                  <option value="">Select agent…</option>
                  {(agents.data ?? []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <Field label="Alert threshold (0–1)">
              <input
                className={inputClass}
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.alert_threshold ?? 0.8}
                onChange={(e) =>
                  setForm((f) => ({ ...f, alert_threshold: Number(e.target.value) }))
                }
              />
            </Field>
          </div>
          {formError && (
            <div className="mt-3">
              <ErrorState error={new Error(formError)} />
            </div>
          )}
          <div className="mt-4">
            <Button disabled={createBudget.isPending} onClick={submit}>
              {createBudget.isPending ? "Saving…" : "Save budget"}
            </Button>
          </div>
        </div>

        {budgets.isLoading && <Skeleton className="h-24" />}
        {budgets.isError && <ErrorState error={budgets.error} />}
        {budgets.data && budgets.data.length === 0 && (
          <EmptyState
            title="No budgets yet"
            body="Create a tenant or agent budget above. FinOps will track spend against it."
          />
        )}
        {budgets.data && budgets.data.length > 0 && (
          <div className="space-y-2">
            {budgets.data.map((b) => {
              const pct = Math.min(100, Math.round((b.pct_used ?? 0) * 100));
              return (
                <div
                  key={b.id}
                  className="rounded-2xl border border-[var(--line)] bg-white px-4 py-3 shadow-[var(--shadow-sm)]"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 text-[13px] font-medium">
                        {b.name}
                        {!b.is_active && <StatusBadge status="suspended" />}
                        {b.over_threshold && <StatusBadge status="degraded" />}
                      </div>
                      <div className="text-[11px] text-[var(--ink-muted)]">
                        {b.scope}
                        {b.agent_name ? ` · ${b.agent_name}` : ""} · {b.period} · alert{" "}
                        {Math.round((b.alert_threshold ?? 0) * 100)}%
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right text-[13px] tabular">
                        ${(b.computed_spent_usd ?? b.spent_usd).toFixed(4)} / $
                        {b.limit_usd.toFixed(2)}
                        <div className="text-[11px] text-[var(--ink-muted)]">{pct}% used</div>
                      </div>
                      {b.is_active && (
                        <Button
                          variant="ghost"
                          className="!px-2.5 !py-1 text-[11px]"
                          disabled={deactivate.isPending}
                          onClick={() => deactivate.mutate(b.id)}
                        >
                          Deactivate
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
                    <div
                      className={`h-full rounded-full ${
                        b.over_threshold ? "bg-amber-500" : "bg-[var(--accent)]"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-[15px] font-semibold">Control plane health</h2>
        {health.isLoading && <Skeleton className="h-16" />}
        {health.isError && <ErrorState error={health.error} />}
        {health.data && (
          <div className="flex items-center gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3">
            <StatusBadge status={health.data.status === "ok" ? "healthy" : health.data.status} />
            <span className="text-[13px] text-[var(--ink-muted)]">{health.data.service}</span>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-[15px] font-semibold">Connectors</h2>
        {connectors.isLoading && <Skeleton className="h-32" />}
        {connectors.isError && <ErrorState error={connectors.error} />}
        {connectors.data && connectors.data.length === 0 && (
          <EmptyState title="No connectors" body="Connect platforms under Connected Platforms, or use Onboarding Studio." />
        )}
        {connectors.data && connectors.data.length > 0 && (
          <div className="space-y-2">
            {connectors.data.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-white px-4 py-3"
              >
                <div>
                  <div className="font-medium text-[13px]">{c.name}</div>
                  <div className="font-mono text-[11px] text-[var(--ink-muted)]">
                    {c.connector_type} · {c.base_url}
                  </div>
                </div>
                <StatusBadge status={c.status} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

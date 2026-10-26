import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
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
import type { Agent, AgentInvokeResponse, Execution, Trace } from "../lib/types";

export function AgentProfilePage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [payload, setPayload] = useState(
    '{\n  "task": "improve",\n  "use_sample": true\n}',
  );
  const [invokeResult, setInvokeResult] = useState<AgentInvokeResponse | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);

  const agent = useQuery({
    queryKey: ["agent", id],
    queryFn: () => api<Agent>(`/api/v1/agents/${id}`),
    enabled: Boolean(id),
  });

  const executions = useQuery({
    queryKey: ["executions", id],
    queryFn: () => api<Execution[]>(`/api/v1/executions?agent_id=${id}&limit=20`),
    enabled: Boolean(id),
  });

  const capabilities = useQuery({
    queryKey: ["capabilities", id],
    queryFn: () => api<Record<string, unknown>>(`/api/v1/agents/${id}/capabilities`),
    enabled: Boolean(id),
    retry: false,
  });

  const trace = useQuery({
    queryKey: ["trace", selectedTrace],
    queryFn: () => api<Trace>(`/api/v1/traces/${selectedTrace}`),
    enabled: Boolean(selectedTrace),
  });

  const invoke = useMutation({
    mutationFn: async () => {
      let input: Record<string, unknown> = {};
      try {
        input = JSON.parse(payload) as Record<string, unknown>;
      } catch {
        throw new Error("Invoke payload must be valid JSON");
      }
      return api<AgentInvokeResponse>(`/api/v1/agents/${id}/invoke`, {
        method: "POST",
        body: JSON.stringify({ input, config: {} }),
      });
    },
    onSuccess: (data) => {
      setInvokeResult(data);
      void qc.invalidateQueries({ queryKey: ["executions", id] });
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
    },
  });

  if (agent.isLoading) return <Skeleton className="h-96" />;
  if (agent.isError) return <ErrorState error={agent.error} />;
  if (!agent.data) return <EmptyState title="Agent not found" body="This agent id is not in the registry." />;

  const a = agent.data;

  return (
    <div>
      <div className="mb-2">
        <Link to="/agents" className="text-[13px] text-[var(--accent)] hover:underline">
          ← Agent Universe
        </Link>
      </div>
      <PageHeader
        eyebrow="Engineering profile"
        title={a.name}
        subtitle={a.description ?? `${a.platform} · ${a.framework} · ${a.environment}`}
      />

      <div className="mb-6 flex flex-wrap gap-2">
        <StatusBadge status={a.lifecycle_state} />
        <StatusBadge status={a.health_status} />
        <StatusBadge status={a.evaluation_status} />
        <span className="inline-flex rounded-full border border-[var(--line)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--ink-muted)]">
          risk {a.risk_class}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="text-[15px] font-semibold">Identity</h2>
          <dl className="mt-4 space-y-2 text-[13px]">
            {[
              ["Owner", a.owner ?? "—"],
              ["Team", a.team ?? "—"],
              ["Domain", a.domain ?? "—"],
              ["External ID", a.external_id ?? "—"],
              ["Invoke URL", a.invoke_url ?? "—"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-[var(--line-soft)] py-2 last:border-0">
                <dt className="text-[var(--ink-muted)]">{k}</dt>
                <dd className="max-w-[60%] truncate text-right font-mono text-[12px]">{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="text-[15px] font-semibold">Invoke</h2>
          <Field label="JSON input">
            <textarea
              className={`${inputClass} mt-1 min-h-[120px] font-mono text-[12px]`}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
            />
          </Field>
          <div className="mt-3 flex items-center gap-3">
            <Button disabled={invoke.isPending} onClick={() => invoke.mutate()}>
              {invoke.isPending ? "Invoking…" : "Invoke agent"}
            </Button>
            {invoke.isError && (
              <span className="text-[12px] text-red-600">
                {invoke.error instanceof Error ? invoke.error.message : "Invoke failed"}
              </span>
            )}
          </div>
          {invokeResult && (
            <pre className="mt-4 max-h-48 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px] text-[var(--ink)]">
              {JSON.stringify(invokeResult, null, 2)}
            </pre>
          )}
        </section>
      </div>

      <section className="mt-6 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
        <h2 className="text-[15px] font-semibold">Capabilities</h2>
        {capabilities.isError && (
          <p className="mt-3 text-[13px] text-[var(--ink-muted)]">
            Capabilities unavailable for this agent.
          </p>
        )}
        {capabilities.data && (
          <pre className="mt-3 max-h-56 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px]">
            {JSON.stringify(capabilities.data, null, 2)}
          </pre>
        )}
      </section>

      <section className="mt-6 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
        <h2 className="mb-4 text-[15px] font-semibold">Recent executions & traces</h2>
        {executions.isLoading && <Skeleton className="h-24" />}
        {executions.isError && <ErrorState error={executions.error} />}
        {executions.data && executions.data.length === 0 && (
          <EmptyState title="No executions yet" body="Invoke this agent to generate traces." />
        )}
        {executions.data && executions.data.length > 0 && (
          <div className="space-y-2">
            {executions.data.map((ex) => (
              <button
                key={ex.id}
                type="button"
                onClick={() => setSelectedTrace(ex.id)}
                className="flex w-full items-center justify-between rounded-xl border border-[var(--line)] px-4 py-3 text-left hover:bg-[var(--bg-muted)]"
              >
                <div>
                  <div className="font-mono text-[12px] text-[var(--ink)]">{ex.id.slice(0, 8)}…</div>
                  <div className="text-[11px] text-[var(--ink-muted)]">
                    {new Date(ex.created_at).toLocaleString()} · {ex.latency_ms ?? "—"} ms
                  </div>
                </div>
                <StatusBadge status={ex.status} />
              </button>
            ))}
          </div>
        )}
        {selectedTrace && (
          <div className="mt-4">
            <h3 className="mb-2 text-[13px] font-semibold">Trace waterfall</h3>
            {trace.isLoading && <Skeleton className="h-20" />}
            {trace.isError && <ErrorState error={trace.error} />}
            {trace.data && (
              <div className="space-y-1">
                {(trace.data.spans?.length ? trace.data.spans : [{ name: "root", duration_ms: 0 }]).map(
                  (span, i) => {
                    const dur = Number(span.duration_ms ?? 0);
                    const width = Math.min(100, Math.max(8, dur / 10));
                    return (
                      <div key={i} className="flex items-center gap-3 text-[12px]">
                        <div className="w-36 truncate font-mono text-[var(--ink-muted)]">
                          {String(span.name ?? `span-${i}`)}
                        </div>
                        <div className="h-2 flex-1 rounded-full bg-[var(--bg-muted)]">
                          <div
                            className="h-2 rounded-full bg-[#0071e3]"
                            style={{ width: `${width}%` }}
                          />
                        </div>
                        <div className="w-16 text-right tabular text-[var(--ink-muted)]">{dur} ms</div>
                      </div>
                    );
                  },
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

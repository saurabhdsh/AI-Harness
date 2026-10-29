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
import type {
  Agent,
  AgentActivitySummary,
  AgentInvokeResponse,
  AgentSkillAttachment,
  Execution,
  LifecycleActionResult,
  Skill,
  Trace,
} from "../lib/types";

export function AgentProfilePage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [payload, setPayload] = useState(
    '{\n  "task": "improve",\n  "use_sample": true\n}',
  );
  const [invokeResult, setInvokeResult] = useState<AgentInvokeResponse | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [skillSlug, setSkillSlug] = useState("");
  const [attachSkillId, setAttachSkillId] = useState("");
  const [rollbackVersion, setRollbackVersion] = useState("");
  const [lifecycleMsg, setLifecycleMsg] = useState("");
  const [lifecycleError, setLifecycleError] = useState("");

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

  const activity = useQuery({
    queryKey: ["agent-activity", id],
    queryFn: () => api<AgentActivitySummary>(`/api/v1/agents/${id}/activity?window_days=30`),
    enabled: Boolean(id),
  });

  const trace = useQuery({
    queryKey: ["trace", selectedTrace],
    queryFn: () => api<Trace>(`/api/v1/traces/${selectedTrace}`),
    enabled: Boolean(selectedTrace),
  });

  const attachedSkills = useQuery({
    queryKey: ["agent-skills", id],
    queryFn: () => api<AgentSkillAttachment[]>(`/api/v1/skills/by-agent/${id}`),
    enabled: Boolean(id),
  });

  const catalog = useQuery({
    queryKey: ["skills"],
    queryFn: () => api<Skill[]>("/api/v1/skills"),
  });

  const attachSkill = useMutation({
    mutationFn: async () => {
      if (!attachSkillId) throw new Error("Select a skill");
      return api<AgentSkillAttachment>(`/api/v1/skills/by-agent/${id}`, {
        method: "POST",
        body: JSON.stringify({ skill_id: attachSkillId, config: {} }),
      });
    },
    onSuccess: () => {
      setAttachSkillId("");
      void qc.invalidateQueries({ queryKey: ["agent-skills", id] });
    },
  });

  const detachSkill = useMutation({
    mutationFn: (skillId: string) =>
      api<void>(`/api/v1/skills/by-agent/${id}/${skillId}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["agent-skills", id] }),
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
        body: JSON.stringify({
          input,
          config: {},
          skill_slug: skillSlug || null,
        }),
      });
    },
    onSuccess: (data) => {
      setInvokeResult(data);
      void qc.invalidateQueries({ queryKey: ["executions", id] });
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
    },
  });

  const lifecycle = useMutation({
    mutationFn: async ({
      operation,
      body,
    }: {
      operation: string;
      body?: Record<string, unknown>;
    }) => {
      const path =
        operation === "delete_source"
          ? `/api/v1/agents/${id}/delete-source`
          : operation === "deploy"
            ? `/api/v1/agents/${id}/deploy`
            : operation === "rollback"
              ? `/api/v1/agents/${id}/rollback`
              : `/api/v1/agents/${id}/lifecycle/${operation}`;
      return api<LifecycleActionResult>(path, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      });
    },
    onSuccess: (data) => {
      setLifecycleError("");
      if (data.status === "awaiting_approval") {
        setLifecycleMsg(
          `Delete submitted for approval (${data.approval_id ?? "pending"}). Decide in Governance Center.`,
        );
      } else {
        setLifecycleMsg(`${data.operation} → ${data.status}`);
      }
      void qc.invalidateQueries({ queryKey: ["agent", id] });
      void qc.invalidateQueries({ queryKey: ["agents"] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: (err) => {
      setLifecycleMsg("");
      setLifecycleError(err instanceof Error ? err.message : "Lifecycle action failed");
    },
  });

  if (agent.isLoading) return <Skeleton className="h-96" />;
  if (agent.isError) return <ErrorState error={agent.error} />;
  if (!agent.data) return <EmptyState title="Agent not found" body="This agent id is not in the registry." />;

  const a = agent.data;
  const caps = capabilities.data ?? {};
  const platformHint = `${a.platform} ${a.framework}`.toLowerCase();
  const isBedrock = platformHint.includes("bedrock");
  const isCopilot = platformHint.includes("copilot");
  const writeCapableDefault = isBedrock || isCopilot;
  const canSuspend = Boolean(caps.suspension) || writeCapableDefault;
  const canResume = Boolean(caps.resume ?? caps.suspension) || writeCapableDefault;
  const canRestart = Boolean(caps.restart ?? caps.suspension) || writeCapableDefault;
  const canDeploy = Boolean(caps.deployment) || writeCapableDefault;
  const canRollback = Boolean(caps.rollback) || isBedrock;
  const canDeleteSource = Boolean(caps.delete_source) || writeCapableDefault;
  const hasLifecycle = Boolean(a.external_id);

  return (
    <div>
      <div className="mb-2">
        <Link to="/agents" className="text-[13px] text-[var(--accent)] hover:underline">
          ← Agent Registry
        </Link>
      </div>
      <PageHeader
        eyebrow="Registry registration"
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

      {hasLifecycle && (
        <section className="mb-6 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="text-[15px] font-semibold">Source platform controls</h2>
          <p className="mt-1 text-[12px] text-[var(--ink-muted)]">
            Start, stop, restart, deploy, rollback, or delete in the connected platform when the
            connector supports it ({a.platform}/{a.framework}).
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {canResume && (
              <Button
                variant="ghost"
                disabled={lifecycle.isPending}
                onClick={() => lifecycle.mutate({ operation: "start" })}
              >
                Start / Resume
              </Button>
            )}
            {canSuspend && (
              <Button
                variant="ghost"
                disabled={lifecycle.isPending}
                onClick={() => lifecycle.mutate({ operation: "stop" })}
              >
                Stop / Suspend
              </Button>
            )}
            {canRestart && (
              <Button
                variant="ghost"
                disabled={lifecycle.isPending}
                onClick={() => lifecycle.mutate({ operation: "restart" })}
              >
                Restart
              </Button>
            )}
            {canDeploy && (
              <Button
                disabled={lifecycle.isPending}
                onClick={() => lifecycle.mutate({ operation: "deploy" })}
              >
                Deploy version
              </Button>
            )}
            {canDeleteSource && (
              <Button
                variant="ghost"
                disabled={lifecycle.isPending}
                onClick={() => {
                  if (
                    !window.confirm(
                      `Request deletion of ${a.name} (${a.external_id}) in the source platform? This creates an approval.`,
                    )
                  ) {
                    return;
                  }
                  lifecycle.mutate({
                    operation: "delete_source",
                    body: {
                      confirm_delete_source: true,
                      create_approval: true,
                      justification: `Delete ${a.external_id} from ${a.platform}`,
                    },
                  });
                }}
              >
                Delete from source…
              </Button>
            )}
          </div>
          {canRollback && (
            <div className="mt-4 flex flex-wrap items-end gap-2">
              <div className="min-w-[160px] flex-1">
                <Field label="Rollback to version">
                  <input
                    className={inputClass}
                    value={rollbackVersion}
                    onChange={(e) => setRollbackVersion(e.target.value)}
                    placeholder="e.g. 2"
                  />
                </Field>
              </div>
              <Button
                variant="ghost"
                disabled={lifecycle.isPending || !rollbackVersion.trim()}
                onClick={() =>
                  lifecycle.mutate({
                    operation: "rollback",
                    body: { version: rollbackVersion.trim() },
                  })
                }
              >
                Roll back
              </Button>
            </div>
          )}
          {lifecycle.isPending && (
            <p className="mt-3 text-[13px] text-[var(--ink-muted)]">Running lifecycle action…</p>
          )}
          {lifecycleMsg && <p className="mt-3 text-[13px] text-[var(--ink-muted)]">{lifecycleMsg}</p>}
          {lifecycleError && <p className="mt-3 text-[13px] text-red-600">{lifecycleError}</p>}
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
          <h2 className="text-[15px] font-semibold">Identity & registration</h2>
          <dl className="mt-4 space-y-2 text-[13px]">
            {[
              ["Owner", a.owner ?? "—"],
              ["Team", a.team ?? "—"],
              ["Domain", a.domain ?? "—"],
              ["External ID", a.external_id ?? "—"],
              ["Blueprint", a.blueprint_id ?? (a.metadata?.blueprint_slug as string) ?? "—"],
              ["Source", (a.metadata?.source as string) ?? "—"],
              ["Git repo", (a.metadata?.git_repo as string) ?? "—"],
              ["Git SHA", (a.metadata?.git_sha as string) ?? "—"],
              ["Pipeline", (a.metadata?.pipeline_id as string) ?? "—"],
              ["Invoke URL", a.invoke_url ?? "—"],
              ["Connection", a.connection_id ?? "—"],
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
          <Field label="Skill (optional)">
            <select
              className={`${inputClass} mt-1`}
              value={skillSlug}
              onChange={(e) => {
                setSkillSlug(e.target.value);
                const att = (attachedSkills.data ?? []).find(
                  (x) => x.skill?.slug === e.target.value,
                );
                if (att?.skill?.sample_input) {
                  setPayload(JSON.stringify(att.skill.sample_input, null, 2));
                }
              }}
            >
              <option value="">All attached skills</option>
              {(attachedSkills.data ?? []).map((a) => (
                <option key={a.id} value={a.skill?.slug ?? a.skill_id}>
                  {a.skill?.name ?? a.skill_id}
                </option>
              ))}
            </select>
          </Field>
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-semibold">Attached skills</h2>
          <Link to="/skills" className="text-[12px] text-[var(--accent)] hover:underline">
            Open Skill Forge →
          </Link>
        </div>
        {attachedSkills.isLoading && <Skeleton className="mt-3 h-16" />}
        {attachedSkills.data && attachedSkills.data.length === 0 && (
          <p className="mt-3 text-[13px] text-[var(--ink-muted)]">
            No skills attached. Attach from Skill Forge or below.
          </p>
        )}
        {attachedSkills.data && attachedSkills.data.length > 0 && (
          <ul className="mt-3 space-y-2">
            {attachedSkills.data.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-[var(--line)] px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium">
                    {a.skill?.name ?? a.skill_id}
                  </div>
                  <div className="font-mono text-[11px] text-[var(--ink-muted)]">
                    {a.skill?.slug} · {a.skill?.domain} · v{a.skill?.version}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  disabled={detachSkill.isPending}
                  onClick={() => detachSkill.mutate(a.skill_id)}
                >
                  Detach
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <div className="min-w-[220px] flex-1">
            <Field label="Attach from catalog">
              <select
                className={`${inputClass} mt-1`}
                value={attachSkillId}
                onChange={(e) => setAttachSkillId(e.target.value)}
              >
                <option value="">Select skill…</option>
                {(catalog.data ?? [])
                  .filter(
                    (s) =>
                      !(attachedSkills.data ?? []).some((a) => a.skill_id === s.id),
                  )
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      [{s.domain}] {s.name}
                    </option>
                  ))}
              </select>
            </Field>
          </div>
          <Button
            disabled={!attachSkillId || attachSkill.isPending}
            onClick={() => attachSkill.mutate()}
          >
            {attachSkill.isPending ? "Attaching…" : "Attach"}
          </Button>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
        <h2 className="text-[15px] font-semibold">Activity</h2>
        <p className="mt-1 text-[12px] text-[var(--ink-muted)]">
          Sessions, exceptions, runtime, and users over the last 30 days.
        </p>
        {activity.isLoading && <Skeleton className="mt-3 h-24" />}
        {activity.isError && <ErrorState error={activity.error} />}
        {activity.data && (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Sessions", activity.data.sessions],
                ["Exceptions", activity.data.exceptions],
                ["Runtime (h)", activity.data.runtime_hours.toFixed(2)],
                ["Unique users", activity.data.unique_users],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl border border-[var(--line-soft)] bg-[var(--bg-muted)] px-3 py-3"
                >
                  <div className="text-[11px] uppercase tracking-wide text-[var(--ink-muted)]">
                    {label}
                  </div>
                  <div className="mt-1 text-[20px] font-semibold tabular-nums">{value}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-3 text-[12px] text-[var(--ink-muted)]">
              <span>Invocations: {activity.data.invocations}</span>
              <span>Tool calls: {activity.data.tool_calls}</span>
              {Object.keys(activity.data.by_source).length > 0 && (
                <span>
                  Sources:{" "}
                  {Object.entries(activity.data.by_source)
                    .map(([src, m]) => `${src}(${m.sessions ?? m.invocations ?? 0})`)
                    .join(", ")}
                </span>
              )}
            </div>
            {activity.data.note && (
              <p className="mt-2 text-[12px] text-[var(--ink-muted)]">{activity.data.note}</p>
            )}
            {activity.data.daily.length > 0 && (
              <div className="mt-4 max-h-48 overflow-auto">
                <table className="w-full text-left text-[12px]">
                  <thead className="sticky top-0 bg-white text-[var(--ink-muted)]">
                    <tr>
                      <th className="py-1 font-medium">Day</th>
                      <th className="py-1 font-medium">Source</th>
                      <th className="py-1 font-medium">Sessions</th>
                      <th className="py-1 font-medium">Exceptions</th>
                      <th className="py-1 font-medium">Users</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activity.data.daily.slice(0, 30).map((row) => (
                      <tr key={`${row.day}-${row.source}`} className="border-t border-[var(--line-soft)]">
                        <td className="py-1 font-mono">{row.day}</td>
                        <td className="py-1">{row.source}</td>
                        <td className="py-1 tabular-nums">{row.sessions}</td>
                        <td className="py-1 tabular-nums">{row.exceptions}</td>
                        <td className="py-1 tabular-nums">{row.unique_users}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

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

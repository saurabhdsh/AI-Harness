import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
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
import type { Agent, AgentSkillAttachment, Skill } from "../lib/types";

const DOMAINS = ["ALL", "AD", "AMS", "QE"] as const;

export function SkillForgePage() {
  const qc = useQueryClient();
  const [domain, setDomain] = useState<(typeof DOMAINS)[number]>("ALL");
  const [selected, setSelected] = useState<Skill | null>(null);
  const [attachAgentId, setAttachAgentId] = useState("");

  const skills = useQuery({
    queryKey: ["skills", domain],
    queryFn: () =>
      api<Skill[]>(
        domain === "ALL" ? "/api/v1/skills" : `/api/v1/skills?domain=${domain}`,
      ),
  });

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<Agent[]>("/api/v1/agents"),
  });

  const seed = useMutation({
    mutationFn: () =>
      api<{ created: number; total: number }>("/api/v1/skills/seed", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["skills"] }),
  });

  const attach = useMutation({
    mutationFn: async () => {
      if (!selected || !attachAgentId) throw new Error("Pick a skill and agent");
      return api<AgentSkillAttachment>(`/api/v1/skills/by-agent/${attachAgentId}`, {
        method: "POST",
        body: JSON.stringify({ skill_id: selected.id, config: {} }),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agent-skills"] });
    },
  });

  const grouped = useMemo(() => {
    const list = skills.data ?? [];
    const map = new Map<string, Skill[]>();
    for (const s of list) {
      const key = s.domain || "OTHER";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(s);
    }
    return map;
  }, [skills.data]);

  return (
    <div>
      <PageHeader
        eyebrow="Enterprise reusable skills"
        title="Skill Forge"
        subtitle="Versioned skill contracts for AD, AMS, and QE. Attach to agents — invoke and eval inject them automatically."
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {DOMAINS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDomain(d)}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
              domain === d
                ? "bg-[#1d1d1f] text-white"
                : "border border-[var(--line)] bg-white text-[var(--ink-muted)] hover:bg-[var(--bg-muted)]"
            }`}
          >
            {d}
          </button>
        ))}
        <div className="flex-1" />
        <Button
          variant="ghost"
          disabled={seed.isPending}
          onClick={() => seed.mutate()}
        >
          {seed.isPending ? "Seeding…" : "Seed built-ins"}
        </Button>
        {seed.data && (
          <span className="text-[12px] text-[var(--ink-muted)]">
            +{seed.data.created} · {seed.data.total} total
          </span>
        )}
      </div>

      {skills.isLoading && (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      )}
      {skills.isError && <ErrorState error={skills.error} />}
      {skills.data && skills.data.length === 0 && (
        <EmptyState
          title="No skills yet"
          body="Seed the built-in AD / AMS / QE catalog to get started."
        />
      )}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          {[...grouped.entries()].map(([dom, items]) => (
            <section key={dom}>
              <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-faint)]">
                {dom}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {items.map((s) => {
                  const active = selected?.id === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSelected(s)}
                      className={`rounded-2xl border bg-white p-4 text-left shadow-[var(--shadow-sm)] transition-colors ${
                        active
                          ? "border-[#1d1d1f]"
                          : "border-[var(--line)] hover:border-[var(--ink-muted)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-[13px]">{s.name}</div>
                        <StatusBadge status={s.risk_class} />
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-[var(--ink-muted)]">
                        {s.slug} · v{s.version}
                      </div>
                      <p className="mt-2 line-clamp-2 text-[12px] text-[var(--ink-muted)]">
                        {s.description || "—"}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-1">
                        {(s.tags || []).slice(0, 4).map((t) => (
                          <span
                            key={t}
                            className="rounded-md bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] text-[var(--ink-muted)]"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        <aside className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)] lg:sticky lg:top-6 lg:self-start">
          {!selected ? (
            <EmptyState
              title="Select a skill"
              body="Inspect the contract, sample input, and attach it to an onboarded agent."
            />
          ) : (
            <>
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-faint)]">
                Contract
              </div>
              <h3 className="mt-1 text-[17px] font-semibold tracking-tight">{selected.name}</h3>
              <p className="mt-1 text-[13px] text-[var(--ink-muted)]">{selected.description}</p>

              <div className="mt-4 flex flex-wrap gap-2">
                <StatusBadge status={selected.domain} />
                <StatusBadge status={selected.risk_class} />
                {selected.is_builtin && <StatusBadge status="healthy" />}
              </div>

              <h4 className="mt-5 text-[12px] font-semibold">Instructions</h4>
              <pre className="mt-2 max-h-40 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-[var(--ink)]">
                {selected.instructions}
              </pre>

              <h4 className="mt-4 text-[12px] font-semibold">Sample input</h4>
              <pre className="mt-2 max-h-28 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px]">
                {JSON.stringify(selected.sample_input, null, 2)}
              </pre>

              <h4 className="mt-4 text-[12px] font-semibold">Output shape</h4>
              <pre className="mt-2 max-h-28 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px]">
                {JSON.stringify(selected.output_schema, null, 2)}
              </pre>

              <div className="mt-5 border-t border-[var(--line-soft)] pt-4">
                <Field label="Attach to agent">
                  <select
                    className={`${inputClass} mt-1`}
                    value={attachAgentId}
                    onChange={(e) => setAttachAgentId(e.target.value)}
                  >
                    <option value="">Select agent…</option>
                    {(agents.data ?? []).map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                        {a.domain ? ` (${a.domain})` : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    disabled={!attachAgentId || attach.isPending}
                    onClick={() => attach.mutate()}
                  >
                    {attach.isPending ? "Attaching…" : "Attach skill"}
                  </Button>
                  {attachAgentId && (
                    <Link
                      to={`/agents/${attachAgentId}`}
                      className="text-[12px] text-[var(--accent)] hover:underline"
                    >
                      Open agent profile →
                    </Link>
                  )}
                </div>
                {attach.isError && (
                  <p className="mt-2 text-[12px] text-red-600">
                    {attach.error instanceof Error ? attach.error.message : "Attach failed"}
                  </p>
                )}
                {attach.isSuccess && (
                  <p className="mt-2 text-[12px] text-emerald-700">Attached. Invokes will inject this skill.</p>
                )}
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

import { useNavigate } from "react-router-dom";
import type { Agent } from "../lib/types";

function healthScore(agent: Agent): number {
  const h = agent.health_status.toLowerCase();
  if (h === "healthy") return 92;
  if (h === "degraded") return 55;
  if (h === "unhealthy") return 22;
  return 40;
}

function confidence(agent: Agent): number {
  const l = agent.lifecycle_state.toLowerCase();
  if (l === "production") return 1;
  if (l === "approved" || l === "validated") return 0.75;
  if (l === "registered") return 0.5;
  return 0.25;
}

export function AgentConstellation({ agents }: { agents: Agent[] }) {
  const nav = useNavigate();

  if (agents.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--line)] p-10 text-center text-[13px] text-[var(--ink-muted)]">
        No agents to visualize yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--bg-muted)]/40 p-6">
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-8">
        {agents.map((n) => {
          const conf = confidence(n);
          const size = Math.round(72 + Math.min(conf, 1) * 28);
          const score = healthScore(n);
          const scoreColor = score >= 70 ? "#34d399" : score >= 40 ? "#fbbf24" : "#f87171";
          return (
            <button
              key={n.id}
              type="button"
              onClick={() => nav(`/agents/${n.id}`)}
              className="flex flex-col items-center gap-2"
              title={`${n.name} · ${n.health_status}`}
            >
              <div
                className="flex shrink-0 items-center justify-center rounded-full border border-[var(--line)] bg-[var(--bg-elev)] shadow-[var(--shadow)] transition hover:border-coral"
                style={{ width: size, height: size }}
              >
                <span
                  className="font-serif font-bold tabular leading-none"
                  style={{ fontSize: Math.round(size * 0.32), color: scoreColor }}
                >
                  {score}
                </span>
              </div>
              <div className="w-24 text-center text-[10px] leading-tight text-[var(--ink-muted)]">
                {n.name}
              </div>
              <div className="text-[9px] text-[var(--ink-muted)] opacity-60">{n.domain ?? n.platform}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

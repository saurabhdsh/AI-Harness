import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../stores/auth";

function UserCard({ onSignOut }: { onSignOut: () => void }) {
  const { user } = useAuth();
  if (!user) return null;

  const username = user.email?.replace("@harness.local", "") ?? user.email ?? "";
  const displayName = username
    .split(/[._-]/)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");

  const parts = displayName.split(" ").filter(Boolean);
  const initials =
    parts.length >= 2 ? parts[0][0] + parts[parts.length - 1][0] : displayName.slice(0, 2);

  return (
    <div className="border-t border-[var(--line)] px-4 py-4">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#1d1d1f] text-[11px] font-semibold uppercase tracking-wide text-white">
          {initials.toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-[var(--ink)]">{displayName}</div>
          <div className="truncate text-[11px] text-[var(--ink-muted)]">
            {user.role} · @{username}
          </div>
        </div>
        <button
          type="button"
          onClick={onSignOut}
          className="shrink-0 rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-white hover:text-[var(--ink)]"
          title="Sign out"
        >
          <LogOut size={14} />
        </button>
      </div>
    </div>
  );
}

const links = [
  { to: "/", label: "Mission Control", end: true },
  { to: "/agents", label: "Agent Universe" },
  { to: "/onboarding", label: "Onboarding Studio" },
  { to: "/workbench", label: "Engineering Workbench" },
  { to: "/evaluations", label: "Evaluation Lab" },
  { to: "/releases", label: "Release Command" },
  { to: "/observatory", label: "Live Observatory" },
  { to: "/finops", label: "FinOps Intelligence" },
  { to: "/governance", label: "Governance Center" },
  { to: "/reliability", label: "Reliability Center" },
  { to: "/workflows", label: "Workflow Orchestration" },
  { to: "/admin", label: "Administration" },
];

export function MissionShell() {
  const { logout } = useAuth();
  const nav = useNavigate();

  const handleSignOut = () => {
    logout();
    nav("/login");
  };

  return (
    <div className="app-bg min-h-screen">
      <div className="grid min-h-screen lg:grid-cols-[220px_1fr]">
        <aside
          className="hidden border-r border-[var(--line)] bg-[var(--bg-muted)] lg:flex lg:flex-col"
          style={{ height: "100vh", position: "sticky", top: 0 }}
        >
          <div className="shrink-0 px-6 py-6">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--ink-faint)]">
              HARNESS
            </div>
            <div
              className="mt-0.5 text-[17px] font-semibold text-[var(--ink)]"
              style={{ letterSpacing: "-0.022em" }}
            >
              AI Engineering
            </div>
          </div>

          <nav
            className="flex flex-col gap-0.5 overflow-y-auto px-2"
            style={{ flex: "1 1 0", minHeight: 0 }}
          >
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? "bg-white text-[var(--ink)] shadow-[var(--shadow-sm)]"
                      : "text-[var(--ink-muted)] hover:bg-white/60 hover:text-[var(--ink)]"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <div className="shrink-0">
            <UserCard onSignOut={handleSignOut} />
          </div>
        </aside>

        <div className="flex min-w-0 flex-col overflow-x-hidden">
          <header className="flex items-center border-b border-[var(--line)] bg-white/80 px-8 py-3 backdrop-blur-xl">
            <div className="text-[13px] font-medium text-[var(--ink-muted)]">
              Federated agent engineering control plane
            </div>
          </header>
          <main className="min-w-0 flex-1 overflow-x-hidden px-6 py-8 sm:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState, type ComponentType } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FlaskConical,
  GitBranch,
  Hammer,
  LayoutDashboard,
  LogOut,
  PanelLeft,
  Radar,
  Scale,
  Settings,
  ShieldAlert,
  Sparkles,
  Wallet,
  type LucideProps,
} from "lucide-react";
import { useAuth } from "../stores/auth";

const SIDEBAR_KEY = "harness_sidebar_collapsed";

type NavIcon = ComponentType<LucideProps>;

const links: Array<{
  to: string;
  label: string;
  icon: NavIcon;
  end?: boolean;
}> = [
  { to: "/", label: "Mission Control", icon: LayoutDashboard, end: true },
  { to: "/agents", label: "Agent Universe", icon: Boxes },
  { to: "/onboarding", label: "Onboarding Studio", icon: ClipboardCheck },
  { to: "/workbench", label: "Engineering Workbench", icon: Hammer },
  { to: "/evaluations", label: "Evaluation Lab", icon: FlaskConical },
  { to: "/skills", label: "Skill Forge", icon: Sparkles },
  { to: "/releases", label: "Release Command", icon: GitBranch },
  { to: "/observatory", label: "Live Observatory", icon: Radar },
  { to: "/finops", label: "FinOps Intelligence", icon: Wallet },
  { to: "/governance", label: "Governance Center", icon: Scale },
  { to: "/reliability", label: "Reliability Center", icon: ShieldAlert },
  { to: "/workflows", label: "Workflow Orchestration", icon: Activity },
  { to: "/admin", label: "Administration", icon: Settings },
];

function UserCard({
  onSignOut,
  collapsed,
}: {
  onSignOut: () => void;
  collapsed: boolean;
}) {
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

  if (collapsed) {
    return (
      <div className="border-t border-[var(--line)] px-2 py-3">
        <div className="flex flex-col items-center gap-2">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-full bg-[#1d1d1f] text-[11px] font-semibold uppercase tracking-wide text-white"
            title={`${displayName} · ${user.role}`}
          >
            {initials.toUpperCase()}
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-white hover:text-[var(--ink)]"
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    );
  }

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

function SidebarNav({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav
      className={`flex flex-col gap-0.5 overflow-y-auto ${collapsed ? "px-1.5" : "px-2"}`}
      style={{ flex: "1 1 0", minHeight: 0 }}
    >
      {links.map((l) => {
        const Icon = l.icon;
        return (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            title={l.label}
            onClick={onNavigate}
            className={({ isActive }) =>
              `rounded-lg text-[13px] font-medium transition-colors ${
                collapsed
                  ? "flex items-center justify-center px-0 py-2.5"
                  : "flex items-center gap-2.5 px-3 py-2"
              } ${
                isActive
                  ? "bg-white text-[var(--ink)] shadow-[var(--shadow-sm)]"
                  : "text-[var(--ink-muted)] hover:bg-white/60 hover:text-[var(--ink)]"
              }`
            }
          >
            <Icon size={collapsed ? 18 : 15} strokeWidth={1.75} className="shrink-0" />
            {!collapsed && <span className="truncate">{l.label}</span>}
          </NavLink>
        );
      })}
    </nav>
  );
}

export function MissionShell() {
  const { logout } = useAuth();
  const nav = useNavigate();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const handleSignOut = () => {
    logout();
    nav("/login");
  };

  const sidebarWidth = collapsed ? 72 : 220;

  return (
    <div className="app-bg min-h-screen">
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside
          className="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-[var(--line)] bg-[var(--bg-muted)] transition-[width] duration-200 ease-out lg:flex"
          style={{ width: sidebarWidth }}
        >
          <div className={`shrink-0 ${collapsed ? "px-2 py-4" : "px-4 py-5"}`}>
            <div className={`flex items-start ${collapsed ? "flex-col items-center gap-2" : "justify-between gap-2"}`}>
              <div className={collapsed ? "text-center" : "min-w-0"}>
                <div
                  className={`font-semibold text-[var(--ink)] ${collapsed ? "text-[15px]" : "text-[20px]"}`}
                  style={{ letterSpacing: collapsed ? "-0.02em" : "-0.03em" }}
                  title="KEEL"
                >
                  {collapsed ? "K" : "KEEL"}
                </div>
                {!collapsed && (
                  <div className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-faint)]">
                    Harness Engineering
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setCollapsed((c) => !c)}
                className="rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-white hover:text-[var(--ink)]"
                title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-expanded={!collapsed}
              >
                {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
              </button>
            </div>
          </div>

          <SidebarNav collapsed={collapsed} />
          <div className="shrink-0">
            <UserCard onSignOut={handleSignOut} collapsed={collapsed} />
          </div>
        </aside>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col overflow-x-hidden">
          <header className="flex items-center gap-3 border-b border-[var(--line)] bg-white/80 px-4 py-3 backdrop-blur-xl sm:px-8">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--ink)] lg:hidden"
              title="Open menu"
              aria-label="Open menu"
            >
              <PanelLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => setCollapsed((c) => !c)}
              className="hidden rounded-md p-1.5 text-[var(--ink-muted)] transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--ink)] lg:inline-flex"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <PanelLeft size={16} />
            </button>
            <div className="text-[13px] font-medium text-[var(--ink-muted)]">
              Federated agent engineering control plane
            </div>
          </header>
          <main className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 sm:px-8 sm:py-8">
            <Outlet />
          </main>
        </div>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/25"
            aria-label="Close menu"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute bottom-0 left-0 top-0 flex w-[min(260px,85vw)] flex-col border-r border-[var(--line)] bg-[var(--bg-muted)] shadow-lg">
            <div className="flex items-center justify-between px-4 py-4">
              <div>
                <div className="text-[20px] font-semibold text-[var(--ink)]" style={{ letterSpacing: "-0.03em" }}>
                  KEEL
                </div>
                <div className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-faint)]">
                  Harness Engineering
                </div>
              </div>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="rounded-md p-1.5 text-[var(--ink-muted)] hover:bg-white"
                aria-label="Close"
              >
                <ChevronLeft size={16} />
              </button>
            </div>
            <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
            <UserCard onSignOut={handleSignOut} collapsed={false} />
          </aside>
        </div>
      )}
    </div>
  );
}

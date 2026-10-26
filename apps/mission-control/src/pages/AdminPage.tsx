import { useQuery } from "@tanstack/react-query";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Connector } from "../lib/types";
import { useAuth } from "../stores/auth";

export function AdminPage() {
  const { user } = useAuth();
  const connectors = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api<Connector[]>("/api/v1/connectors"),
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string; service: string }>("/api/v1/health"),
  });

  return (
    <div>
      <PageHeader
        eyebrow="Platform"
        title="Administration"
        subtitle="Tenant identity, connectors, and control-plane health."
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
        <p className="mt-3 text-[12px] text-[var(--ink-faint)]">
          Full user/role administration APIs are planned. This view shows the active JWT principal only.
        </p>
      </div>

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
          <EmptyState
            title="No connectors"
            body="Create connections via Onboarding Studio."
          />
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

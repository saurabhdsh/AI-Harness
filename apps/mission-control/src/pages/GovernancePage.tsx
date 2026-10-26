import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { api } from "../lib/api";
import type { Approval, AuditEvent } from "../lib/types";

export function GovernancePage() {
  const qc = useQueryClient();
  const approvals = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api<Approval[]>("/api/v1/approvals"),
  });
  const audit = useQuery({
    queryKey: ["audit-events"],
    queryFn: () => api<AuditEvent[]>("/api/v1/audit-events?limit=50"),
  });

  const decide = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "approved" | "rejected" }) =>
      api(`/api/v1/approvals/${id}/decide`, {
        method: "POST",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
      void qc.invalidateQueries({ queryKey: ["release-board"] });
      void qc.invalidateQueries({ queryKey: ["release-promotions"] });
      void qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  return (
    <div>
      <PageHeader
        eyebrow="Control"
        title="Governance Center"
        subtitle="Approvals and audit events from the control plane."
      />

      <section className="mb-10">
        <h2 className="mb-3 text-[15px] font-semibold">Approvals</h2>
        {approvals.isLoading && <Skeleton className="h-32" />}
        {approvals.isError && <ErrorState error={approvals.error} />}
        {approvals.data && approvals.data.length === 0 && (
          <EmptyState title="No approval requests" body="Pending and historical approvals appear here." />
        )}
        {approvals.data && approvals.data.length > 0 && (
          <div className="space-y-2">
            {approvals.data.map((a) => (
              <div
                key={a.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-3 shadow-[var(--shadow-sm)]"
              >
                <div>
                  <div className="font-medium text-[13px]">{a.action}</div>
                  <div className="text-[11px] text-[var(--ink-muted)]">
                    {a.justification ?? "No justification"} · {new Date(a.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={a.status} />
                  {a.status === "pending" && (
                    <>
                      <Button
                        variant="soft"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: a.id, status: "approved" })}
                      >
                        Approve
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: a.id, status: "rejected" })}
                      >
                        Reject
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-[15px] font-semibold">Audit events</h2>
        {audit.isLoading && <Skeleton className="h-32" />}
        {audit.isError && <ErrorState error={audit.error} />}
        {audit.data && audit.data.length === 0 && (
          <EmptyState title="No audit events" body="Control-plane actions will stream into this log." />
        )}
        {audit.data && audit.data.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-[var(--line)] bg-[var(--bg-muted)] text-[11px] uppercase tracking-[0.12em] text-[var(--ink-muted)]">
                <tr>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Resource</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.map((e) => (
                  <tr key={e.id} className="border-b border-[var(--line-soft)] last:border-0">
                    <td className="px-4 py-3 text-[var(--ink-muted)]">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px]">{e.action}</td>
                    <td className="px-4 py-3 text-[var(--ink-muted)]">
                      {e.resource_type ?? "—"} {e.resource_id ? `· ${e.resource_id.slice(0, 8)}…` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

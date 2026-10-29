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
import type { Connector, ConnectorSyncResult } from "../lib/types";

const PLATFORMS: Array<{
  id: string;
  label: string;
  basePlaceholder: string;
  secretPlaceholder: string;
  hint: string;
}> = [
  {
    id: "aws_bedrock",
    label: "AWS Bedrock Agents",
    basePlaceholder: "https://bedrock.us-east-1.amazonaws.com",
    secretPlaceholder: "vault:tenant/aws or leave empty for ambient AWS_* env",
    hint: "Enter region endpoint + AWS credentials (secret ref or control-plane AWS env). Then Validate → Sync agents.",
  },
  {
    id: "copilot_studio",
    label: "Microsoft Copilot Studio",
    basePlaceholder: "https://org.crm.dynamics.com",
    secretPlaceholder: "bearer:<dataverse-token> or COPILOT_STUDIO_TOKEN env",
    hint: "Power Platform / Dataverse environment URL + bearer token with bots read. Sync inventories Copilot Studio agents; invoke stays on Direct Line / CI invoke_url.",
  },
  {
    id: "azure_foundry",
    label: "Azure AI Foundry",
    basePlaceholder: "https://<resource>.services.ai.azure.com/api/projects/<project>",
    secretPlaceholder: "vault:tenant/azure or bearer:<token>",
    hint: "Use the Azure AI project endpoint and a secret ref for the API key / Entra credential.",
  },
  {
    id: "servicenow",
    label: "ServiceNow AI Agents",
    basePlaceholder: "https://<instance>.service-now.com",
    secretPlaceholder: "basic:user:pass or bearer:<token> or vault:tenant/sn",
    hint: "Instance URL + credentials. Sync discovers ServiceNow AI agents into the registry.",
  },
  {
    id: "mulesoft",
    label: "MuleSoft Agent Fabric",
    basePlaceholder: "https://<agent-fabric-or-api>.example.com",
    secretPlaceholder: "oauth:<client_id>:<client_secret> or vault:tenant/mule",
    hint: "Agent Fabric / runtime base URL with OAuth or vault secret ref.",
  },
  {
    id: "generic_rest",
    label: "Generic REST",
    basePlaceholder: "https://agents.example.com",
    secretPlaceholder: "vault://… (optional)",
    hint: "Any HTTP agent fleet exposing /agents or OpenAPI invoke paths.",
  },
  {
    id: "langgraph",
    label: "LangGraph HTTP",
    basePlaceholder: "http://127.0.0.1:8090",
    secretPlaceholder: "vault://… (optional)",
    hint: "Self-hosted LangGraph HTTP service.",
  },
  {
    id: "crewai",
    label: "CrewAI HTTP",
    basePlaceholder: "http://127.0.0.1:8091",
    secretPlaceholder: "vault://… (optional)",
    hint: "Self-hosted CrewAI HTTP service.",
  },
];

export function ConnectedPlatformsPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState("aws_bedrock");
  const [baseUrl, setBaseUrl] = useState("https://bedrock.us-east-1.amazonaws.com");
  const [secretRef, setSecretRef] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [createError, setCreateError] = useState("");
  const [collectObservability, setCollectObservability] = useState(true);

  const selected = useMemo(
    () => PLATFORMS.find((p) => p.id === connectorType) ?? PLATFORMS[0],
    [connectorType],
  );

  const connectors = useQuery({
    queryKey: ["connectors"],
    queryFn: () => api<Connector[]>("/api/v1/connectors"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<Connector>("/api/v1/connectors", {
        method: "POST",
        body: JSON.stringify({
          name,
          connector_type: connectorType,
          base_url: baseUrl,
          secret_ref: secretRef || null,
          collect_observability: collectObservability,
          metadata: { source: "connected_platforms" },
        }),
      }),
    onSuccess: () => {
      setName("");
      setCreateError("");
      void qc.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (err) => {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    },
  });

  const validate = useMutation({
    mutationFn: (id: string) =>
      api<{ ok: boolean; error?: string }>(`/api/v1/connectors/${id}/validate`, {
        method: "POST",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["connectors"] }),
  });

  const sync = useMutation({
    mutationFn: (id: string) =>
      api<ConnectorSyncResult>(`/api/v1/connectors/${id}/sync`, { method: "POST" }),
    onSuccess: (res) => {
      setSyncMsg(
        res.status === "completed"
          ? `Synced ${res.registered_agent_ids.length} new, ${res.updated_agent_ids.length} updated`
          : res.error || "Sync failed",
      );
      void qc.invalidateQueries({ queryKey: ["connectors"] });
      void qc.invalidateQueries({ queryKey: ["agents"] });
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
    },
    onError: (err) => {
      setSyncMsg(err instanceof Error ? err.message : "Sync failed");
    },
  });

  const toggleObs = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api<Connector>(`/api/v1/connectors/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ collect_observability: enabled }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["connectors"] });
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
    },
  });

  const collectObs = useMutation({
    mutationFn: (id: string) =>
      api<{ status: string; snapshots_upserted: number; error?: string | null }>(
        `/api/v1/connectors/${id}/collect-observability`,
        { method: "POST" },
      ),
    onSuccess: (res) => {
      setSyncMsg(
        res.error
          ? res.error
          : `Collected ${res.snapshots_upserted} activity snapshot(s) (${res.status})`,
      );
      void qc.invalidateQueries({ queryKey: ["mission-overview"] });
    },
    onError: (err) => {
      setSyncMsg(err instanceof Error ? err.message : "Collect observability failed");
    },
  });

  return (
    <div>
      <PageHeader
        eyebrow="Onboard · cloud platforms"
        title="Connected Platforms"
        subtitle="Connect a platform → Validate → Sync agents into the KEEL registry."
      />

      <ol className="mb-6 list-decimal space-y-1 pl-5 text-[13px] text-[var(--ink-muted)]">
        <li>Choose the external platform (e.g. Amazon Bedrock).</li>
        <li>Enter endpoint / region context and credential secret ref.</li>
        <li>
          Click <span className="font-medium text-[var(--ink)]">Connect</span>, then{" "}
          <span className="font-medium text-[var(--ink)]">Validate</span>.
        </li>
        <li>
          Click <span className="font-medium text-[var(--ink)]">Sync agents</span> — inventory lands in{" "}
          <Link to="/agents" className="text-[var(--accent)] hover:underline">
            Agent Registry
          </Link>
          .
        </li>
      </ol>

      <p className="mb-6 text-[13px] text-[var(--ink-muted)]">
        Git-built agents (CI register / catalog): use{" "}
        <Link to="/onboarding" className="font-medium text-[var(--accent)] hover:underline">
          Onboarding Studio
        </Link>
        .
      </p>

      <section className="mb-8 rounded-2xl border border-[var(--line)] bg-white p-6 shadow-[var(--shadow-sm)]">
        <h2 className="mb-1 text-[15px] font-semibold">Connect a platform</h2>
        <p className="mb-4 text-[12px] text-[var(--ink-muted)]">{selected.hint}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Display name">
            <input
              className={inputClass}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="AWS Bedrock prod"
            />
          </Field>
          <Field label="Platform">
            <select
              className={inputClass}
              value={connectorType}
              onChange={(e) => {
                const next = e.target.value;
                setConnectorType(next);
                const meta = PLATFORMS.find((p) => p.id === next);
                if (meta) setBaseUrl(meta.basePlaceholder.startsWith("http") ? meta.basePlaceholder : "");
              }}
            >
              {PLATFORMS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Base URL / endpoint">
            <input
              className={inputClass}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={selected.basePlaceholder}
            />
          </Field>
          <Field label="Secret ref (no plaintext secrets)">
            <input
              className={inputClass}
              value={secretRef}
              onChange={(e) => setSecretRef(e.target.value)}
              placeholder={selected.secretPlaceholder}
            />
          </Field>
        </div>
        <label className="mt-4 flex cursor-pointer items-start gap-2 text-[13px]">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={collectObservability}
            onChange={(e) => setCollectObservability(e.target.checked)}
          />
          <span>
            <span className="font-medium text-[var(--ink)]">Collect observability</span>
            <span className="block text-[12px] text-[var(--ink-muted)]">
              Pull Activity (sessions, exceptions, runtime, users) on Sync.
            </span>
          </span>
        </label>
        <div className="mt-4 flex items-center gap-3">
          <Button
            disabled={!name.trim() || !baseUrl.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Connecting…" : "Connect"}
          </Button>
          {createError && <p className="text-[13px] text-red-600">{createError}</p>}
        </div>
      </section>

      {syncMsg && (
        <p className="mb-4 text-[13px] text-[var(--ink-muted)]">
          {syncMsg}{" "}
          <Link to="/agents" className="font-medium text-[var(--accent)] hover:underline">
            Open Agent Registry
          </Link>
        </p>
      )}

      {connectors.isLoading && <Skeleton className="h-40" />}
      {connectors.isError && <ErrorState error={connectors.error} />}
      {connectors.data && connectors.data.length === 0 && (
        <EmptyState
          title="No connected platforms"
          body="Connect a cloud platform above, then Validate and Sync agents."
        />
      )}

      {connectors.data && connectors.data.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-[15px] font-semibold">Connected</h2>
          {connectors.data.map((c) => (
            <div
              key={c.id}
              className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-white px-4 py-4 shadow-[var(--shadow-sm)] sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-[14px]">{c.name}</span>
                  <StatusBadge status={c.status} />
                  {c.last_sync_status && <StatusBadge status={c.last_sync_status} />}
                </div>
                <div className="mt-1 font-mono text-[11px] text-[var(--ink-muted)]">
                  {c.connector_type} · {c.base_url}
                </div>
                <div className="mt-1 text-[12px] text-[var(--ink-muted)]">
                  Synced agents: {c.synced_agent_count ?? 0}
                  {c.last_synced_at
                    ? ` · last sync ${new Date(c.last_synced_at).toLocaleString()}`
                    : " · never synced"}
                  {c.collect_observability !== false ? " · obs on" : " · obs off"}
                </div>
                {(c.last_sync_error || c.last_error) && (
                  <p className="mt-1 text-[12px] text-red-600">
                    {c.last_sync_error || c.last_error}
                  </p>
                )}
                <label className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-[var(--ink-muted)]">
                  <input
                    type="checkbox"
                    checked={c.collect_observability !== false}
                    disabled={toggleObs.isPending}
                    onChange={(e) =>
                      toggleObs.mutate({ id: c.id, enabled: e.target.checked })
                    }
                  />
                  Collect observability
                </label>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button
                  variant="ghost"
                  disabled={validate.isPending}
                  onClick={() => validate.mutate(c.id)}
                >
                  Validate
                </Button>
                <Button
                  disabled={sync.isPending}
                  onClick={() => {
                    setSyncMsg("");
                    sync.mutate(c.id);
                  }}
                >
                  {sync.isPending ? "Syncing…" : "Sync agents"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={collectObs.isPending || c.collect_observability === false}
                  onClick={() => {
                    setSyncMsg("");
                    collectObs.mutate(c.id);
                  }}
                >
                  {collectObs.isPending ? "Collecting…" : "Collect activity"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

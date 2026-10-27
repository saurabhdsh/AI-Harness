import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Field, inputClass, PageHeader, StatusBadge } from "../components/ui";
import { FlowProgress, type FlowStep, type FlowStepStatus } from "../components/FlowProgress";
import { InvokeOutcomeTheater } from "../components/InvokeOutcomeTheater";
import { api, getToken } from "../lib/api";
import type {
  AgentInvokeResponse,
  EvaluationRun,
  OnboardingJobResult,
  Trace,
} from "../lib/types";

type Source = "path" | "upload" | "cloud" | "ci";
type Phase = "source" | "detect" | "configure" | "running" | "complete" | "failed";

type Detection = {
  root?: string;
  primary?: string | null;
  confidence?: number;
  recommended_connector?: string | null;
  frameworks?: Array<{ id: string; score: number }>;
  invoke_hints?: string[];
  entrypoints?: string[];
  files_scanned?: number;
  evidence?: Array<{ framework: string; evidence: string; file?: string | null }>;
  cloud_targets?: string[];
  notes?: string[];
  upload_id?: string;
  project_root?: string;
};

type ConnectorInfo = { id: string; label: string; connector_type: string };

const RUNWAY = [
  { id: "detect", label: "Understand agent project" },
  { id: "connect", label: "Validate platform connection" },
  { id: "discover", label: "Discover / register agent" },
  { id: "invoke", label: "Smoke invoke" },
  { id: "trace", label: "Capture trace" },
  { id: "evaluate", label: "Evaluation gate" },
  { id: "govern", label: "Update mission posture" },
] as const;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

const DEFAULT_PATH =
  "/Users/saurabhdubey/AI-Harness/examples/langgraph-openai-agent";

export function OnboardingStudioPage() {
  const qc = useQueryClient();
  const [phase, setPhase] = useState<Phase>("source");
  const [source, setSource] = useState<Source>("path");
  const [path, setPath] = useState(DEFAULT_PATH);
  const [file, setFile] = useState<File | null>(null);
  const [detection, setDetection] = useState<Detection | null>(null);
  const [detectError, setDetectError] = useState("");
  const [detecting, setDetecting] = useState(false);

  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState("langgraph");
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8090");
  const [secretRef, setSecretRef] = useState("");
  const [externalId, setExternalId] = useState("");
  const [domain, setDomain] = useState("ad");
  const [environment, setEnvironment] = useState("dev");
  const [owner, setOwner] = useState("platform-engineer");
  const [team, setTeam] = useState("ad-engineering");
  const [invokeUrl, setInvokeUrl] = useState("http://127.0.0.1:8091/agents/ad-user-story/invoke");
  const [gitRepo, setGitRepo] = useState("https://github.com/org/agent-service");
  const [gitRef, setGitRef] = useState("main");
  const [gitSha, setGitSha] = useState("");
  const [ciResult, setCiResult] = useState<{
    agent_id: string;
    created: boolean;
    external_id: string;
    invoke_url: string;
  } | null>(null);

  const [statuses, setStatuses] = useState<Record<string, FlowStepStatus>>(
    Object.fromEntries(RUNWAY.map((s) => [s.id, "pending" as FlowStepStatus])),
  );
  const [details, setDetails] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [onboard, setOnboard] = useState<OnboardingJobResult | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [invokeResult, setInvokeResult] = useState<AgentInvokeResponse | null>(null);
  const [invokePending, setInvokePending] = useState(false);
  const [evalRun, setEvalRun] = useState<EvaluationRun | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);

  const frameworks = useQuery({
    queryKey: ["onboarding-frameworks"],
    queryFn: () =>
      api<{ connectors: ConnectorInfo[]; frameworks: string[] }>("/api/v1/onboarding/frameworks"),
  });

  const steps: FlowStep[] = useMemo(
    () =>
      RUNWAY.map((d) => ({
        id: d.id,
        label: d.label,
        status: statuses[d.id] ?? "pending",
        detail: details[d.id],
      })),
    [statuses, details],
  );

  const isCloudConnector =
    connectorType === "aws_bedrock" ||
    connectorType === "azure_foundry" ||
    connectorType === "servicenow" ||
    connectorType === "mulesoft";

  const mark = (id: string, status: FlowStepStatus, detail?: string) => {
    setStatuses((prev) => ({ ...prev, [id]: status }));
    if (detail !== undefined) setDetails((prev) => ({ ...prev, [id]: detail }));
  };

  const runDetect = async () => {
    setDetectError("");
    setDetecting(true);
    setDetection(null);
    try {
      let result: Detection;
      if (source === "path") {
        result = await api<Detection>("/api/v1/onboarding/detect/path", {
          method: "POST",
          body: JSON.stringify({ path }),
        });
      } else if (source === "upload") {
        if (!file) throw new Error("Choose a .zip of the agent project");
        const fd = new FormData();
        fd.append("file", file);
        const token = getToken();
        const res = await fetch("/api/v1/onboarding/detect/upload", {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: fd,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(String(body.detail || res.statusText));
        }
        result = (await res.json()) as Detection;
      } else if (source === "ci") {
        result = {
          primary: connectorType || "generic_rest",
          recommended_connector: connectorType || "generic_rest",
          confidence: 1,
          frameworks: [{ id: connectorType || "generic_rest", score: 1 }],
          notes: [
            "Git / CI path — agent was built from a repo and deployed by your pipeline.",
            "Harness registers the deployed invoke URL (upsert by external_id). No local folder scan.",
            "Prefer calling POST /api/v1/onboarding/ci/register from CI after deploy.",
          ],
        };
        if (!name) setName("CI-registered agent");
        if (!connectorType) setConnectorType("generic_rest");
        setConnectorType((c) => c || "generic_rest");
      } else {
        result = {
          primary: connectorType,
          recommended_connector: connectorType,
          confidence: 1,
          frameworks: [{ id: connectorType, score: 1 }],
          notes: ["Cloud platform selected — provide endpoint / credentials next."],
          cloud_targets: [connectorType],
        };
      }

      setDetection(result);
      if (result.recommended_connector) setConnectorType(result.recommended_connector);
      if (result.primary && !name) {
        setName(
          result.primary === "langgraph"
            ? "AD OpenAI Code Engineer"
            : `${result.primary} agent`,
        );
      }
      if (result.primary === "langgraph" && !baseUrl) {
        setBaseUrl("http://127.0.0.1:8090");
      }
      if (result.primary === "crewai" && !baseUrl) {
        setBaseUrl("http://127.0.0.1:8091");
      }
      setPhase("configure");
    } catch (err) {
      setDetectError(err instanceof Error ? err.message : "Detection failed");
    } finally {
      setDetecting(false);
    }
  };

  const runFullFlow = async () => {
    setPhase("running");
    setError("");
    setOnboard(null);
    setCiResult(null);
    setInvokeResult(null);
    setInvokePending(false);
    setEvalRun(null);
    setTrace(null);
    setStatuses(Object.fromEntries(RUNWAY.map((s) => [s.id, "pending" as FlowStepStatus])));
    setDetails({});

    try {
      mark(
        "detect",
        "done",
        detection?.primary
          ? `${detection.primary} · confidence ${Math.round((detection.confidence ?? 0) * 100)}%`
          : source === "ci"
            ? "CI / Git deploy provenance"
            : "Cloud / manual connector",
      );

      // Enterprise CI path — upsert deployed agent by external_id (no local folder)
      if (source === "ci") {
        if (!externalId.trim()) throw new Error("external_id is required for CI registration");
        if (!invokeUrl.trim()) throw new Error("invoke_url is required for CI registration");

        mark("connect", "active", "CI post-deploy register");
        mark("discover", "active", `Upsert ${externalId}`);
        const reg = await api<{
          agent_id: string;
          connection_id: string | null;
          created: boolean;
          external_id: string;
          invoke_url: string;
        }>("/api/v1/onboarding/ci/register", {
          method: "POST",
          body: JSON.stringify({
            name: name || externalId,
            external_id: externalId,
            invoke_url: invokeUrl,
            connector_type: connectorType || "generic_rest",
            framework: connectorType || "generic_rest",
            base_url: baseUrl || null,
            secret_ref: secretRef || null,
            domain,
            environment,
            owner,
            team,
            git_repo: gitRepo || null,
            git_ref: gitRef || null,
            git_sha: gitSha || null,
            create_connection: true,
          }),
        });
        setCiResult(reg);
        setAgentId(reg.agent_id);
        mark("connect", "done", reg.created ? "Connection created" : "Connection reused");
        mark(
          "discover",
          "done",
          reg.created ? `Registered ${reg.external_id}` : `Updated ${reg.external_id}`,
        );

        const id = reg.agent_id;
        mark("invoke", "active", "Smoke invoke via registered URL");
        setInvokePending(true);
        const invocation = await api<AgentInvokeResponse>(`/api/v1/agents/${id}/invoke`, {
          method: "POST",
          body: JSON.stringify({
            input: { task: "analyze", use_sample: true },
            config: {},
          }),
        });
        setInvokeResult(invocation);
        setInvokePending(false);
        if (invocation.status !== "succeeded") {
          mark("invoke", "error", invocation.error || "Invoke failed");
          throw new Error(invocation.error || "Invoke failed");
        }
        mark(
          "invoke",
          "done",
          `${Math.round(invocation.latency_ms ?? 0)} ms · smoke ok`,
        );

        mark("trace", "active", "Loading spans");
        const t = await api<Trace>(`/api/v1/traces/${invocation.execution_id}`);
        setTrace(t);
        mark("trace", "done", `${t.spans?.length ?? 0} span(s)`);

        mark("evaluate", "done", "Skipped — CI path uses smoke invoke; run Evaluation Lab for gates");
        mark("govern", "active", "Refreshing mission");
        await qc.invalidateQueries({ queryKey: ["mission-overview"] });
        await qc.invalidateQueries({ queryKey: ["agents"] });
        mark("govern", "done", "Agent visible in Universe");
        setPhase("complete");
        return;
      }

      mark("connect", "active", isCloudConnector ? "Authenticating cloud connector" : `GET ${baseUrl}/health`);
      await sleep(300);

      mark("discover", "active", "Registering into control-plane registry");
      const job = await api<OnboardingJobResult>("/api/v1/onboarding/projects", {
        method: "POST",
        body: JSON.stringify({
          name: name || "Onboarded agent",
          source,
          project_root: source === "path" ? path : detection?.project_root || detection?.root || null,
          upload_id: detection?.upload_id || null,
          connector_type: connectorType,
          base_url: isCloudConnector && connectorType === "aws_bedrock" ? baseUrl || "" : baseUrl,
          secret_ref: secretRef || null,
          external_id: externalId || null,
          auto_register: true,
          owner,
          team,
          domain,
          environment,
          metadata: { smart_onboarding: true },
          run_invoke_smoke: false,
        }),
      });
      setOnboard(job);
      if (job.status !== "completed") {
        mark("connect", "error", job.error || "Onboarding failed");
        mark("discover", "error", job.error || "Register failed");
        throw new Error(job.error || "Onboarding failed");
      }
      mark("connect", "done", "Connection validated");
      mark(
        "discover",
        "done",
        `${job.discovered.length} discovered · ${job.registered_agent_ids.length} registered`,
      );

      if (!job.registered_agent_ids.length) {
        if (isCloudConnector) {
          mark("invoke", "done", "Skipped — cloud agent registered without HTTP smoke (credentials/discovery only)");
          mark("trace", "done", "Skipped");
          mark("evaluate", "done", "Skipped");
          mark("govern", "active", "Refreshing mission");
          await qc.invalidateQueries({ queryKey: ["mission-overview"] });
          await qc.invalidateQueries({ queryKey: ["agents"] });
          mark("govern", "done", "Registry updated");
          setPhase("complete");
          return;
        }
        throw new Error("No agents registered");
      }

      const id = job.registered_agent_ids[0];
      setAgentId(id);

      mark("invoke", "active", "Live invoke through Harness connector");
      setInvokePending(true);
      const invocation = await api<AgentInvokeResponse>(`/api/v1/agents/${id}/invoke`, {
        method: "POST",
        body: JSON.stringify({
          input: { task: "analyze", use_sample: true },
          config: {},
        }),
      });
      setInvokeResult(invocation);
      setInvokePending(false);
      if (invocation.status !== "succeeded") {
        mark("invoke", "error", invocation.error || "Invoke failed");
        throw new Error(invocation.error || "Invoke failed");
      }
      mark(
        "invoke",
        "done",
        `${Math.round(invocation.latency_ms ?? 0)} ms · ${String(invocation.output?.summary ?? "ok").slice(0, 100)}`,
      );

      mark("trace", "active", "Loading spans");
      const t = await api<Trace>(`/api/v1/traces/${invocation.execution_id}`);
      setTrace(t);
      mark("trace", "done", `${t.spans?.length ?? 0} span(s)`);

      mark("evaluate", "active", "Deterministic evaluation");
      const evaluation = await api<EvaluationRun>("/api/v1/evaluations", {
        method: "POST",
        body: JSON.stringify({
          agent_id: id,
          name: "smart-onboard-gate",
          use_llm_judge: false,
          cases: [
            {
              case_id: "keys-smoke",
              input: { task: "analyze", use_sample: true },
              expected: { summary: "", issues: [] },
              match_mode: "keys",
            },
          ],
        }),
      });
      setEvalRun(evaluation);
      mark(
        "evaluate",
        evaluation.status === "completed" ? "done" : "error",
        `score ${evaluation.aggregate_score ?? "—"} · ${evaluation.summary ?? evaluation.status}`,
      );
      if (evaluation.status !== "completed") throw new Error(evaluation.error || "Evaluation failed");

      mark("govern", "active", "Mission refresh");
      await qc.invalidateQueries({ queryKey: ["mission-overview"] });
      await qc.invalidateQueries({ queryKey: ["agents"] });
      await sleep(250);
      mark("govern", "done", "Agent visible in Universe + Observatory");
      setPhase("complete");
    } catch (err) {
      setInvokePending(false);
      setError(err instanceof Error ? err.message : "Smart onboarding failed");
      setPhase("failed");
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Ingest"
        title="Onboarding Studio"
        subtitle="Enterprise path: register Git-built agents after CI/CD deploy. Lab path: detect a local project or zip. Cloud path: connect Bedrock / Foundry / ServiceNow."
      />

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <motion.section
            layout
            className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-[var(--shadow-sm)]"
          >
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              1 · Source
            </div>
            <div className="mb-4 flex flex-wrap gap-2">
              {(
                [
                  ["ci", "Git / CI deploy"],
                  ["path", "Project path"],
                  ["upload", "Upload zip"],
                  ["cloud", "Cloud platform"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  disabled={phase === "running"}
                  onClick={() => {
                    setSource(id);
                    setPhase("source");
                    setDetection(null);
                    if (id === "ci") setConnectorType("generic_rest");
                  }}
                  className={`rounded-full px-3 py-1.5 text-[12px] font-medium ${
                    source === id
                      ? "bg-[#0071e3] text-white"
                      : "bg-[var(--bg-muted)] text-[var(--ink-muted)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {source === "ci" && (
              <div className="space-y-3">
                <p className="text-[13px] text-[var(--ink-muted)]">
                  For agents built in Git and deployed by your pipeline. Register the{" "}
                  <span className="font-medium text-[var(--ink)]">deployed invoke URL</span> — Harness
                  does not clone the repo. Idempotent on <span className="font-mono">external_id</span>.
                </p>
                <Field label="Stable external id (service / agent key)">
                  <input
                    className={inputClass}
                    value={externalId}
                    disabled={phase === "running"}
                    onChange={(e) => setExternalId(e.target.value)}
                    placeholder="ad-user-story"
                  />
                </Field>
                <Field label="Deployed invoke URL">
                  <input
                    className={inputClass}
                    value={invokeUrl}
                    disabled={phase === "running"}
                    onChange={(e) => setInvokeUrl(e.target.value)}
                    placeholder="https://agents.example.com/agents/ad-user-story/invoke"
                  />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Git repo URL">
                    <input
                      className={inputClass}
                      value={gitRepo}
                      disabled={phase === "running"}
                      onChange={(e) => setGitRepo(e.target.value)}
                      placeholder="https://github.com/org/repo"
                    />
                  </Field>
                  <Field label="Git ref">
                    <input
                      className={inputClass}
                      value={gitRef}
                      disabled={phase === "running"}
                      onChange={(e) => setGitRef(e.target.value)}
                      placeholder="main / v1.2.0"
                    />
                  </Field>
                </div>
                <Field label="Git SHA (optional)">
                  <input
                    className={inputClass}
                    value={gitSha}
                    disabled={phase === "running"}
                    onChange={(e) => setGitSha(e.target.value)}
                    placeholder="abc123…"
                  />
                </Field>
              </div>
            )}
            {source === "path" && (
              <Field label="Absolute path to agent project">
                <input
                  className={inputClass}
                  value={path}
                  disabled={phase === "running"}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="/path/to/my-langgraph-agent"
                />
              </Field>
            )}
            {source === "upload" && (
              <Field label="Agent project (.zip)">
                <input
                  type="file"
                  accept=".zip"
                  disabled={phase === "running"}
                  className="block w-full text-[13px] text-[var(--ink-muted)]"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </Field>
            )}
            {source === "cloud" && (
              <Field label="Cloud connector">
                <select
                  className={inputClass}
                  value={connectorType}
                  disabled={phase === "running"}
                  onChange={(e) => setConnectorType(e.target.value)}
                >
                  <option value="aws_bedrock">AWS Bedrock Agents</option>
                  <option value="azure_foundry">Azure AI Foundry</option>
                  <option value="servicenow">ServiceNow AI Agents</option>
                  <option value="mulesoft">MuleSoft Agent Fabric</option>
                  <option value="langgraph">LangGraph HTTP (self-hosted)</option>
                  <option value="crewai">CrewAI HTTP</option>
                  <option value="generic_rest">Generic REST</option>
                </select>
              </Field>
            )}

            <div className="mt-4">
              <Button onClick={() => void runDetect()} disabled={detecting || phase === "running"}>
                {detecting
                  ? "Analyzing…"
                  : source === "ci"
                    ? "Continue with CI provenance"
                    : "Detect framework"}
              </Button>
            </div>
            {detectError && <p className="mt-3 text-[13px] text-red-600">{detectError}</p>}
          </motion.section>

          {detection && (
            <motion.section
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-[var(--shadow-sm)]"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                  2 · Detection
                </div>
                <StatusBadge status={detection.primary ? "validated" : "unknown"} />
              </div>
              <div className="font-serif text-2xl text-[var(--ink)]">
                {detection.primary ?? "Unknown framework"}
              </div>
              <p className="mt-1 text-[13px] text-[var(--ink-muted)]">
                Confidence {Math.round((detection.confidence ?? 0) * 100)}% · scanned{" "}
                {detection.files_scanned ?? 0} files · connector{" "}
                <span className="font-mono text-[var(--ink)]">
                  {detection.recommended_connector ?? "—"}
                </span>
              </p>

              {!!detection.frameworks?.length && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {detection.frameworks.map((f) => (
                    <span
                      key={f.id}
                      className="rounded-full border border-[var(--line)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--ink)]"
                    >
                      {f.id} · {Math.round(f.score * 100)}%
                    </span>
                  ))}
                </div>
              )}

              {!!detection.notes?.length && (
                <ul className="mt-4 space-y-1 text-[12px] text-[var(--ink-muted)]">
                  {detection.notes.map((n) => (
                    <li key={n}>• {n}</li>
                  ))}
                </ul>
              )}

              {!!detection.evidence?.length && (
                <pre className="mt-4 max-h-36 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[10px]">
                  {JSON.stringify(detection.evidence.slice(0, 8), null, 2)}
                </pre>
              )}
            </motion.section>
          )}

          {(phase === "configure" || phase === "running" || phase === "complete" || phase === "failed") && (
            <motion.section
              layout
              className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-[var(--shadow-sm)]"
            >
              <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
                3 · Connect & register
              </div>
              <div className="space-y-3">
                <Field label="Display name">
                  <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} disabled={phase === "running"} />
                </Field>
                <Field label="Connector">
                  <select
                    className={inputClass}
                    value={connectorType}
                    disabled={phase === "running"}
                    onChange={(e) => setConnectorType(e.target.value)}
                  >
                    {(frameworks.data?.connectors ?? [
                      { id: "langgraph", label: "LangGraph" },
                      { id: "crewai", label: "CrewAI" },
                      { id: "generic_rest", label: "Generic REST" },
                      { id: "aws_bedrock", label: "AWS Bedrock" },
                      { id: "azure_foundry", label: "Azure Foundry" },
                      { id: "servicenow", label: "ServiceNow AI Agents" },
                      { id: "mulesoft", label: "MuleSoft Agent Fabric" },
                    ]).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </Field>

                {!isCloudConnector && source !== "ci" && (
                  <Field label="Running agent base URL">
                    <input
                      className={inputClass}
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      disabled={phase === "running"}
                      placeholder="http://127.0.0.1:8090"
                    />
                  </Field>
                )}

                {source === "ci" && (
                  <>
                    <Field label="External id">
                      <input
                        className={inputClass}
                        value={externalId}
                        onChange={(e) => setExternalId(e.target.value)}
                        disabled={phase === "running"}
                      />
                    </Field>
                    <Field label="Invoke URL">
                      <input
                        className={inputClass}
                        value={invokeUrl}
                        onChange={(e) => setInvokeUrl(e.target.value)}
                        disabled={phase === "running"}
                      />
                    </Field>
                    <Field label="Optional connection base URL">
                      <input
                        className={inputClass}
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        disabled={phase === "running"}
                        placeholder="Derived from invoke URL if empty"
                      />
                    </Field>
                  </>
                )}

                {connectorType === "azure_foundry" && (
                  <Field label="Azure AI project endpoint">
                    <input
                      className={inputClass}
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      disabled={phase === "running"}
                      placeholder="https://<resource>.services.ai.azure.com/api/projects/<project>"
                    />
                  </Field>
                )}

                {connectorType === "servicenow" && (
                  <Field label="ServiceNow instance URL">
                    <input
                      className={inputClass}
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      disabled={phase === "running"}
                      placeholder="https://<instance>.service-now.com"
                    />
                  </Field>
                )}

                {connectorType === "mulesoft" && (
                  <Field label="MuleSoft Agent Fabric / runtime base URL">
                    <input
                      className={inputClass}
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      disabled={phase === "running"}
                      placeholder="https://<agent-fabric-or-api>.example.com"
                    />
                  </Field>
                )}

                {isCloudConnector && (
                  <>
                    <Field label="Secret reference (Vault) — no plaintext secrets">
                      <input
                        className={inputClass}
                        value={secretRef}
                        onChange={(e) => setSecretRef(e.target.value)}
                        disabled={phase === "running"}
                        placeholder={
                          connectorType === "servicenow"
                            ? "basic:user:pass or bearer:<token> or vault:tenant/sn"
                            : connectorType === "mulesoft"
                              ? "oauth:<client_id>:<client_secret> or vault:tenant/mule"
                              : "vault:tenant/aws or vault:tenant/azure"
                        }
                      />
                    </Field>
                    <Field label="External agent id (optional if discovery works)">
                      <input
                        className={inputClass}
                        value={externalId}
                        onChange={(e) => setExternalId(e.target.value)}
                        disabled={phase === "running"}
                        placeholder="Bedrock agent id / Foundry agent id"
                      />
                    </Field>
                  </>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Domain">
                    <input className={inputClass} value={domain} onChange={(e) => setDomain(e.target.value)} disabled={phase === "running"} />
                  </Field>
                  <Field label="Environment">
                    <input className={inputClass} value={environment} onChange={(e) => setEnvironment(e.target.value)} disabled={phase === "running"} />
                  </Field>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button onClick={() => void runFullFlow()} disabled={phase === "running"}>
                  {phase === "running"
                    ? "Running…"
                    : source === "ci"
                      ? "Register from deploy & smoke"
                      : "Onboard & run full flow"}
                </Button>
                {(phase === "complete" || phase === "failed") && (
                  <Button variant="ghost" onClick={() => setPhase("configure")}>
                    Reset
                  </Button>
                )}
                {agentId && (
                  <Link to={`/agents/${agentId}`} className="self-center text-[13px] font-medium text-[#0071e3] hover:underline">
                    Open agent profile →
                  </Link>
                )}
              </div>
            </motion.section>
          )}
        </div>

        <motion.section
          layout
          className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-[var(--shadow-sm)]"
        >
          <div className="mb-1 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
              Engineering runway
            </div>
            {phase !== "source" && phase !== "detect" && phase !== "configure" && (
              <StatusBadge
                status={phase === "complete" ? "succeeded" : phase === "failed" ? "failed" : "running"}
              />
            )}
          </div>
          <div className="mb-5 font-serif text-2xl text-[var(--ink)]">Live progress</div>
          {phase === "source" || phase === "detect" || (phase === "configure" && !onboard && !ciResult) ? (
            <div className="space-y-3 text-[13px] text-[var(--ink-muted)]">
              <p>
                Prefer <span className="font-medium text-[var(--ink)]">Git / CI deploy</span> for production:
                your pipeline builds from Git, deploys the agent, then calls Harness to register the live
                invoke URL. Path/zip remain for lab detection.
              </p>
              <pre className="overflow-x-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[10px] text-[var(--ink)]">
{`# After deploy in CI:
curl -X POST "$HARNESS_API/api/v1/onboarding/ci/register" \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{
    "name": "AD User Story",
    "external_id": "ad-user-story",
    "invoke_url": "https://agents.example.com/agents/ad-user-story/invoke",
    "git_repo": "https://github.com/org/agents",
    "git_sha": "'"$GIT_SHA"'",
    "environment": "prod"
  }'`}
              </pre>
              <p className="text-[12px]">
                Catalog sync: <span className="font-mono">POST /api/v1/onboarding/catalog/sync</span> —
                discover a fleet from one base URL after release.
              </p>
            </div>
          ) : (
            <>
              <FlowProgress steps={steps} />
              <InvokeOutcomeTheater result={invokeResult} pending={invokePending} />
            </>
          )}
          {error && (
            <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[13px] text-red-700">
              {error}
            </p>
          )}
        </motion.section>
      </div>

      <AnimatePresence>
        {(onboard || invokeResult || evalRun) && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 grid gap-6 lg:grid-cols-3"
          >
            <ResultCard title="Registration">
              {onboard && (
                <>
                  <MetaRow label="Status" value={onboard.status} />
                  <MetaRow label="Discovered" value={String(onboard.discovered.length)} />
                  <MetaRow label="Registered" value={String(onboard.registered_agent_ids.length)} />
                  {onboard.detection?.primary && (
                    <MetaRow label="Framework" value={String(onboard.detection.primary)} />
                  )}
                </>
              )}
            </ResultCard>
            <ResultCard title="Invoke">
              {invokeResult ? (
                <>
                  <MetaRow label="Status" value={invokeResult.status} />
                  <MetaRow
                    label="Latency"
                    value={invokeResult.latency_ms != null ? `${Math.round(invokeResult.latency_ms)} ms` : "—"}
                  />
                  <pre className="mt-3 max-h-40 overflow-auto rounded-xl bg-[var(--bg-muted)] p-3 font-mono text-[11px]">
                    {JSON.stringify(invokeResult.output, null, 2)}
                  </pre>
                </>
              ) : (
                <p className="text-[12px] text-[var(--ink-muted)]">Waiting…</p>
              )}
            </ResultCard>
            <ResultCard title="Eval & trace">
              {evalRun && (
                <>
                  <MetaRow label="Eval" value={evalRun.status} />
                  <MetaRow label="Score" value={String(evalRun.aggregate_score ?? "—")} />
                </>
              )}
              {trace && (
                <p className="mt-2 text-[12px] text-[var(--ink-muted)]">
                  {trace.spans?.length ?? 0} spans ·{" "}
                  <Link to="/observatory" className="text-[#0071e3] hover:underline">
                    Observatory
                  </Link>
                </p>
              )}
            </ResultCard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ResultCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-white p-5 shadow-[var(--shadow-sm)]">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">
        {title}
      </div>
      {children}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-[var(--line-soft)] py-1.5 text-[13px]">
      <span className="text-[var(--ink-muted)]">{label}</span>
      <span className="truncate font-medium text-[var(--ink)]">{value}</span>
    </div>
  );
}

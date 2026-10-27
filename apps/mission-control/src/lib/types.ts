export type AuthUser = {
  id: string;
  email: string;
  role: string;
  tenantId: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  tenant_id: string;
  user_id: string;
  email: string;
};

export type MissionOverview = {
  total_agents: number;
  by_lifecycle: Record<string, number>;
  by_health: Record<string, number>;
  by_evaluation: Record<string, number>;
  recent_executions: number;
  failed_executions_24h: number;
  pending_approvals: number;
  total_cost_usd: number;
};

export type Agent = {
  id: string;
  tenant_id: string;
  name: string;
  platform: string;
  framework: string;
  external_id: string | null;
  owner: string | null;
  team: string | null;
  domain: string | null;
  environment: string;
  lifecycle_state: string;
  risk_class: string;
  health_status: string;
  evaluation_status: string;
  connection_id: string | null;
  invoke_url: string | null;
  description: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentInvokeResponse = {
  execution_id: string;
  status: string;
  output: Record<string, unknown>;
  latency_ms: number | null;
  token_input: number | null;
  token_output: number | null;
  trace_id: string | null;
  error: string | null;
};

export type OnboardingJobCreate = {
  name: string;
  connector_type: string;
  base_url: string;
  secret_ref?: string | null;
  auto_register?: boolean;
  owner?: string | null;
  team?: string | null;
  domain?: string | null;
  environment?: string;
  metadata?: Record<string, unknown>;
};

export type OnboardingJobResult = {
  connection_id: string;
  discovered: Array<Record<string, unknown>>;
  registered_agent_ids: string[];
  status: string;
  error: string | null;
  detection?: Record<string, unknown> | null;
};

export type EvaluationCase = {
  case_id: string;
  input: Record<string, unknown>;
  expected?: Record<string, unknown> | null;
  match_mode?: string;
};

export type EvaluationResult = {
  id: string;
  case_id: string;
  input_payload: Record<string, unknown>;
  expected: Record<string, unknown> | null;
  actual: Record<string, unknown> | null;
  score: number;
  passed: boolean;
  metrics: Record<string, unknown>;
  judge_notes: string | null;
};

export type EvaluationRun = {
  id: string;
  tenant_id: string;
  agent_id: string;
  name: string;
  status: string;
  suite: Record<string, unknown>;
  use_llm_judge: boolean;
  aggregate_score: number | null;
  summary: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  results: EvaluationResult[];
};

export type Execution = {
  id: string;
  tenant_id: string;
  agent_id: string;
  status: string;
  request: Record<string, unknown>;
  response: Record<string, unknown> | null;
  latency_ms: number | null;
  token_input: number | null;
  token_output: number | null;
  trace_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type TraceSpan = {
  name?: string;
  span_id?: string;
  parent_id?: string | null;
  start_ms?: number;
  duration_ms?: number;
  status?: string;
  [key: string]: unknown;
};

export type Trace = {
  id: string;
  tenant_id: string;
  execution_id: string;
  spans: TraceSpan[];
  status: string;
  created_at: string;
  updated_at: string;
};

export type CostSummary = {
  total_cost_usd: number;
  total_token_input: number;
  total_token_output: number;
  records: number;
  rate_note?: string;
  budgets_over_threshold?: number;
  active_budgets?: number;
  repaired_records?: number;
};

export type CostRecord = {
  id: string;
  tenant_id: string;
  agent_id: string | null;
  execution_id: string | null;
  cost_usd: number;
  token_input: number;
  token_output: number;
  model_name: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  agent_name?: string | null;
};

export type Budget = {
  id: string;
  tenant_id: string;
  name: string;
  scope: string;
  agent_id: string | null;
  limit_usd: number;
  spent_usd: number;
  period: string;
  alert_threshold: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  computed_spent_usd?: number;
  pct_used?: number;
  remaining_usd?: number;
  over_threshold?: boolean;
  period_start?: string | null;
  agent_name?: string | null;
};

export type BudgetCreate = {
  name: string;
  scope: "tenant" | "agent";
  agent_id?: string | null;
  limit_usd: number;
  period: "daily" | "weekly" | "monthly" | "all_time";
  alert_threshold?: number;
  is_active?: boolean;
};

export type Approval = {
  id: string;
  tenant_id: string;
  agent_id: string | null;
  requested_by: string | null;
  action: string;
  status: string;
  justification: string | null;
  decision_notes: string | null;
  decided_by: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: string;
  tenant_id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export type Connector = {
  id: string;
  tenant_id: string;
  name: string;
  connector_type: string;
  base_url: string;
  secret_ref: string | null;
  capabilities: Record<string, unknown>;
  status: string;
  last_error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ReleaseGate = {
  id: string;
  type: string;
  required: boolean;
  status: string;
  detail?: string | null;
};

export type ReleaseTrain = {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  description: string | null;
  stages: Array<{ env: string; gates?: string[]; approval_for_risk?: string[] }>;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Promotion = {
  id: string;
  tenant_id: string;
  agent_id: string;
  train_id: string | null;
  from_env: string;
  to_env: string;
  status: string;
  gates: ReleaseGate[];
  justification: string | null;
  error: string | null;
  requested_by: string | null;
  approval_id: string | null;
  completed_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  agent_name?: string | null;
  train_name?: string | null;
};

export type ReleaseBoardAgent = {
  id: string;
  name: string;
  domain: string | null;
  lifecycle_state: string;
  evaluation_status: string;
  risk_class: string;
  health_status: string;
};

export type ReleaseBoard = {
  environments: Array<{ environment: string; agents: ReleaseBoardAgent[] }>;
  trains: ReleaseTrain[];
  open_promotions: Promotion[];
};

export type Skill = {
  id: string;
  tenant_id: string;
  slug: string;
  name: string;
  domain: string;
  version: string;
  description: string | null;
  instructions: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  eval_suite: Record<string, unknown>;
  risk_class: string;
  tags: string[];
  sample_input: Record<string, unknown>;
  is_active: boolean;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentSkillAttachment = {
  id: string;
  tenant_id: string;
  agent_id: string;
  skill_id: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  skill?: Skill | null;
};

export type ReliabilityErrorClass = {
  class_id: string;
  label: string;
  count: number;
  share: number;
  sample_error?: string | null;
};

export type ReliabilityAgentRisk = {
  agent_id: string;
  agent_name: string;
  domain: string | null;
  health_status: string;
  total: number;
  failed: number;
  succeeded: number;
  error_rate: number;
  avg_latency_ms: number | null;
  last_failure_at: string | null;
  last_error: string | null;
};

export type ReliabilityTimelineBucket = {
  t: string;
  start: string;
  ok: number;
  fail: number;
  total: number;
};

export type ReliabilityFailureEvent = {
  execution_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  error: string | null;
  error_class: string;
  latency_ms: number | null;
  created_at: string;
  trace_id: string | null;
};

export type ReliabilityLatencyOutlier = {
  execution_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  latency_ms: number;
  created_at: string;
};

export type ReliabilityOverview = {
  window_hours: number;
  window_start: string;
  generated_at: string;
  total_executions: number;
  succeeded: number;
  failed: number;
  running: number;
  success_rate: number;
  error_rate: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  max_latency_ms: number | null;
  agents_invoked: number;
  unhealthy_agents: number;
  degraded_agents: number;
  note: string;
  error_classes: ReliabilityErrorClass[];
  agents_at_risk: ReliabilityAgentRisk[];
  timeline: ReliabilityTimelineBucket[];
  recent_failures: ReliabilityFailureEvent[];
  latency_outliers: ReliabilityLatencyOutlier[];
};

export type WorkflowGraphNode = {
  id: string;
  type: string;
  label: string;
  config?: Record<string, unknown>;
};

export type WorkflowGraphEdge = {
  from: string;
  to: string;
};

export type WorkflowDefinition = {
  id: string;
  tenant_id: string;
  slug: string;
  name: string;
  description: string | null;
  domain: string;
  version: string;
  graph: { nodes: WorkflowGraphNode[]; edges: WorkflowGraphEdge[] };
  sample_input: Record<string, unknown>;
  tags: string[];
  is_active: boolean;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  node_count: number;
  hitl_count: number;
};

export type WorkflowStep = {
  id: string;
  run_id: string;
  node_id: string;
  node_type: string;
  label: string;
  seq: number;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  error: string | null;
  agent_id: string | null;
  execution_id: string | null;
  approval_id: string | null;
  latency_ms: number | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowRun = {
  id: string;
  tenant_id: string;
  definition_id: string;
  name: string;
  status: string;
  input_payload: Record<string, unknown>;
  context: Record<string, unknown>;
  agent_bindings: Record<string, string>;
  current_node_id: string | null;
  error: string | null;
  started_by: string | null;
  pending_approval_id: string | null;
  created_at: string;
  updated_at: string;
  steps: WorkflowStep[];
  definition_name?: string | null;
  definition_slug?: string | null;
  definition_domain?: string | null;
};

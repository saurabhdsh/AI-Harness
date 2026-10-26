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

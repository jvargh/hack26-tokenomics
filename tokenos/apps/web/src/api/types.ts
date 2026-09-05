/** Types mirroring the local TokenOS API contract. */

export interface HealthResponse {
  status: string;
  version: string;
  modelMode: "local" | "foundry";
  foundryAvailable: boolean;
  efficientDeployment: string | null;
  advancedDeployment: string | null;
  workflows: string[];
}

export type HealthState =
  | { state: "checking" }
  | { state: "ready"; health: HealthResponse }
  | { state: "offline"; message: string };

export interface WorkflowRole {
  role: string;
  label: string;
  help: string;
  accept: string;
  multiple: boolean;
  required: boolean;
}

export interface WorkflowField {
  name: string;
  label: string;
  control: "text" | "textarea" | "number" | "select" | "checkbox" | "datetime";
  required: boolean;
  default?: string;
  options?: string[];
  help?: string;
  maxLength?: number;
  min?: number;
  max?: number;
  step?: number;
}

export interface WorkflowDefinition {
  workflow_id: string;
  label: string;
  short_label: string;
  description: string;
  default_outcome: string;
  defaults: {
    importance: string;
    needed: string;
    priority: string;
    maximum_cost_usd: number;
    required_quality_score: number;
  };
  roles: WorkflowRole[];
  fields: WorkflowField[];
  sample: { id: string; name: string; description: string };
  model_use: string;
}

export interface ConnectedApplication {
  application_id: string;
  name: string;
  workflow_id: string;
  adapter: string;
  scope: string;
  permitted_actions: string[];
  reference_label: string;
  reference_example: string;
  available_references: string[];
  connection_kind: "local_stub" | "live";
}

export interface UploadRecord {
  upload_id: string;
  name: string;
  role: string;
  workflow_id: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  status: string;
  data_classification: string;
  extracted_character_count: number;
  detail: Record<string, unknown>;
  origin: "upload" | "sample" | "connected";
}

export interface PlanOperation {
  operation_id: string;
  order: number;
  label: string;
  kind: string;
  reason: string;
  route: string;
  depends_on: number[];
  side_effect: boolean;
  quality_check: string | null;
}

export interface ProtectionCheck {
  check_id: string;
  name: string;
  passed: boolean;
  detail: string;
  evidence: Array<{ label: string; value: string }>;
  reason?: string;
  operation_label?: string;
  user_action?: string;
  prevented?: string;
}

export interface PlanResponse {
  plan_id: string;
  workflow_id: string;
  input_summary: Record<string, unknown>;
  operation_count: number;
  operations: PlanOperation[];
  estimated_model_calls: { minimum: number; maximum: number };
  estimated_maximum_cost_usd: number;
  requires_approval: boolean;
  plan_summary: {
    title: string;
    description: string;
    facts: Array<{ label: string; value: string }>;
  };
  protection_checks: ProtectionCheck[];
  model_available: boolean;
}

export interface VerificationCheckResult {
  name: string;
  rule: string;
  result: string;
  passed: boolean;
}

export interface DecisionFinding {
  document: string;
  line?: string | null;
  finding: string;
  amount_usd: number | null;
  policy_citation: string;
  source_excerpt: string;
  recommendation?: "approve" | "request_evidence" | "needs_interpretation" | "reject";
  resolved_by: string;
}

export interface ReviewedItem {
  document: string;
  line?: string | null;
  label: string;
  amount_usd: number;
  outcome: "approve" | "request_evidence" | "needs_interpretation" | "reject" | "unmatched";
  reason: string;
  policy_citation?: string | null;
  reference?: string | null;
  approval_id?: string | null;
}

export interface Tokenomics {
  actual_cost_usd: number;
  actual_tokens: number;
  projected_cost_usd: number | null;
  projected_input_tokens: number;
  projected_output_tokens: number;
  projected_total_tokens: number;
  avoided_cost_usd: number | null;
  avoided_per_1k_runs_usd: number | null;
  projected_per_1k_runs_usd: number | null;
  actual_per_1k_runs_usd: number;
  estimated_exposure_usd: number | null;
  estimated_exposure_per_1k_runs_usd: number | null;
  exposure_reason: string | null;
  saving_claimable: boolean;
  saving_blocked_reason: string | null;
  quality_passed: boolean;
  avoided_reason: string | null;
  cost_per_accepted_result_usd: number | null;
  projected_cost_per_accepted_result_usd: number | null;
  comparison_deployment: string;
  price_effective_date: string | null;
  price_source: string | null;
  basis: string;
  priced: boolean;
  routing?: {
    total_operations: number;
    operations_without_generative_ai: number;
    operations_reserved_for_a_model: number;
    operations_on_a_model: number;
    model_available: boolean;
    note: string | null;
    rows: Array<{
      route: string;
      route_label: string;
      count: number;
      model_calls?: number;
      why: string;
      operations: string[];
      generative: boolean;
      executed_on_model: number;
      deferred: boolean;
    }>;
  };
  operations: Array<{
    operation_id: string;
    label: string;
    actual_route: string;
    projected_input_tokens: number;
    projected_output_tokens: number;
    projected_cost_usd: number;
    priced: boolean;
  }>;
}

export interface PriceTableEntry {
  input_per_1m_usd: number;
  output_per_1m_usd: number;
  effective_date?: string;
  model?: string;
  model_version?: string;
  region?: string;
  source?: string;
}

export interface FoundryConfig {
  model_mode: string;
  foundry_base_url: string;
  foundry_auth_mode: string;
  foundry_token_scope: string;
  efficient_deployment: string;
  advanced_deployment: string;
  foundry_available: boolean;
  foundry_configured: boolean;
  has_api_key: boolean;
  price_table: Record<string, PriceTableEntry>;
}

export interface FoundryTestResult {
  success: boolean;
  deployment?: string;
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  price_configured?: boolean;
  model_version?: string;
  response_preview?: string;
  error?: string;
}

export interface BaselineRun {
  available: boolean;
  status?: ComparisonStatus;
  reason?: string;
  saving_claimable: boolean;
  saving_usd?: number | null;
  saving_per_1k_runs_usd?: number | null;
  saving_blocked_reason?: string | null;
  equal_quality?: boolean;
  note?: string;
  comparison_contract?: ComparisonContract;
  contract_matched?: boolean | null;
  model_version?: string | null;
  governed: {
    cost_usd: number;
    quality_passed: boolean;
    findings: number;
    model_calls: number;
    tokens: number;
  };
  baseline: {
    cost_usd: number;
    quality_passed: boolean;
    findings: number;
    model_calls: number;
    tokens: number;
    cached_input_tokens?: number;
    reasoning_tokens?: number;
    deployment: string;
    grounded: string;
    amounts_verified: string;
    citations_present: string;
  } | null;
}

export type ComparisonStatus =
  | "not_requested"
  | "running"
  | "eligible_saving"
  | "no_saving"
  | "invalid_comparison"
  | "baseline_failed"
  | "unavailable";

export interface ModelCall {
  route: string;
  deployment: string;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens?: number;
  reasoning_tokens?: number;
  duration_ms: number;
  calculated_cost_usd: number;
  price_configured: boolean;
}

export interface LiveOperation extends PlanOperation {
  status: "pending" | "running" | "complete" | "blocked" | "failed";
  actual_cost_usd?: number;
  duration_ms?: number;
  detail?: Record<string, unknown>;
}

export interface Proof {
  run_id: string;
  plan_id: string;
  workflow_id: string;
  status: string;
  created_at: string;
  finished_at: string;
  input_evidence: string;
  measurement: string;
  measurement_label: string;
  outcome: {
    successful: boolean;
    quality_passed: boolean;
    quality_score: number;
    required_quality_score: number;
    deadline_met: boolean | null;
    decision_complete?: boolean;
    unresolved_items?: number;
    quality_label?: string;
    headline?: string;
  };
  usage: {
    model_calls: number;
    input_tokens: number;
    output_tokens: number;
    duration_ms: number;
    deployments: string[];
    model_mode: string;
  };
  economics: {
    calculated_model_cost_usd: number;
    tool_cost_usd: number;
    total_calculated_cost_usd: number;
    authorized_model_cost_usd: number;
    price_configured: boolean;
    actual_cost_status?: string;
    comparator_status?: string;
    difference_status?: string;
    verified_saving_status?: string;
    token_source?: string;
  };
  routing: {
    operations: number;
    completed_without_generative_ai: number;
    efficient_ai: number;
    advanced_ai: number;
  };
  verification: VerificationCheckResult[];
  facts: Array<{ label: string; value: string; detail?: string }>;
  finding: { type: string; title: string; body: string } | null;
  findings: DecisionFinding[];
  reviewed_items: ReviewedItem[];
  tokenomics: Tokenomics | null;
  baseline: {
    kind: string;
    title?: string;
    status?: string;
    columns: string[];
    rows: string[][];
    note?: string;
  } | null;
  why_ai?: WhyAiRecord[];
  comparison_contract?: ComparisonContract;
  inputs: UploadRecord[];
  operations: LiveOperation[];
  model_calls: ModelCall[];
}

export interface ComparisonContract {
  prompt_version: string;
  output_schema_version: string;
  max_output_tokens: number;
  citation_requirement: string;
  quality_checks: string[];
  test_set: string | null;
  note: string;
}

export interface WhyAiRecord {
  route: string;
  deployment: string;
  why_ai: string;
  input_tokens: number;
  output_tokens: number;
  calculated_cost_usd: number;
  quality_check: { passed: boolean; reason: string } | null;
  token_source: string;
  ceiling_remaining_usd: number;
}

export interface RunMetrics {
  operations_total: number;
  completed: number;
  without_generative_ai: number;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  calculated_model_cost_usd: number;
  authorized_model_cost_usd: number;
  quality_state: string;
  measurement: string;
}

export interface ApprovalRequest {
  action: string;
  reason: string;
  maximum_cost_usd: number;
  rollback: string;
  decision: "pending" | "approved" | "rejected";
}

export interface RunState {
  run_id: string;
  plan_id: string;
  workflow_id: string;
  status: string;
  phase: string;
  created_at: string;
  operations: LiveOperation[];
  metrics: RunMetrics;
  approval: ApprovalRequest | null;
  proof: Proof | null;
  error: { message: string; type: string } | null;
  last_sequence: number;
}

export interface ServerEvent {
  type: string;
  sequence: number;
  run_id: string;
  at: string;
  [key: string]: unknown;
}

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fieldErrors: FieldError[] = []
  ) {
    super(message);
    this.name = "ApiError";
  }
}

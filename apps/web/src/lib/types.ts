/**
 * JevRouter API 的传输类型。
 *
 * 这是 `apps/api/schemas.py` 的手写镜像，不是生成的客户端。API 才是唯一事实来源：
 * 那边的字段一改，这里就必须跟着改。可空性也与 API 一致——存储可能返回 `NULL`
 * 的字段，在这里就是 `| null`，因为「没有概率」和真实的 `0.0` 含义不同，不能
 * 渲染成同一个样子。
 */

/** 一个尚未进入终态的运行。 */
export type LiveStatus = "running" | "awaiting_confirmation" | "awaiting_input";

/** 核心包的 `RunStatus` 可能报告的终态。 */
export type TerminalStatus =
  | "completed"
  | "needs_user_input"
  | "needs_confirmation"
  | "rejected"
  | "budget_exhausted"
  | "failed";

/**
 * 状态以普通字符串传输，因此遇到无法识别的值时必须能存活下来，而不是在运行时
 * 变成类型错误。
 */
export type KnownStatus = LiveStatus | TerminalStatus;

export interface SubmitTaskResponse {
  task_id: string;
  status: string;
}

export interface PendingConfirmationView {
  action: string;
  arguments: unknown;
  step: number;
  /** 这次批准绑定在哪一份参数上；批准时必须原样回传。 */
  digest: string;
  /** 过期时间（ISO 8601）。过期后批准不再生效。 */
  expires_at: string;
}

export interface PendingInputView {
  question: string;
  step: number;
}

export interface TaskSummary {
  task_id: string;
  goal: string;
  status: string;
  step: number;
}

export interface TaskView {
  task_id: string;
  goal: string;
  status: string;
  step: number;
  diagnostic: string | null;
  pending_confirmation: PendingConfirmationView | null;
  pending_input: PendingInputView | null;
}

export interface TaskListResponse {
  tasks: TaskSummary[];
}

/**
 * 一个已完成的步骤，由核心包的 `StepTrace` 展平而来。
 *
 * `arguments`、`result` 与 `state_snapshot` 是这一层并不建模的 JSON 形状，
 * 因此保持 `unknown`，并通过 JSON 查看器渲染。
 */
export interface TraceView {
  step: number;
  action: string;
  policy_outcome: string | null;
  policy_reason: string | null;
  executed: boolean;
  result: unknown;
  route_confidence: number | null;
  route_risk: number | null;
  requires_confirmation: number | null;
  needs_reasoning: number | null;
  confirmed: boolean | null;
  arguments: unknown;
  completion_probability: number | null;
  quality_score: number | null;
  state_snapshot: unknown;
  duration_ms: number;
}

export interface TraceListResponse {
  task_id: string;
  traces: TraceView[];
}

/**
 * 一次评测运行中的一个用例结果，镜像自 `apps/api/schemas.py`。
 *
 * LLM 基线不产生概率，因此它的策略字段为 `null`——「没有升级」和真实的 `false`
 * 是两个不同的事实，不能渲染成同一个样子。
 */
export interface EvalCaseOutcome {
  case_id: string;
  goal: string;
  expected_action: string;
  allowed_actions: string[];
  requires_confirmation: boolean;
  mode: string;
  action: string | null;
  matched_expected: boolean;
  matched_allowed: boolean;
  succeeded: boolean;
  policy_outcome: string | null;
  escalated: boolean | null;
  confirmation_requested: boolean | null;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  error: string | null;
}

export interface EvalLatency {
  mean_ms: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
}

export interface EvalTokenStats {
  mean: number;
  total: number;
}

export interface EvalModeMetrics {
  mode: string;
  case_count: number;
  error_count: number;
  expected_match_count: number;
  allowed_match_count: number;
  success_count: number;
  escalation_count: number | null;
  confirmation_expected_count: number | null;
  confirmation_requested_count: number | null;
  confirmation_match_count: number | null;
  expected_match_rate: number;
  allowed_match_rate: number;
  success_rate: number;
  error_rate: number;
  escalation_rate: number | null;
  latency: EvalLatency;
  input_tokens: EvalTokenStats | null;
  output_tokens: EvalTokenStats | null;
}

export interface EvalComparisonMetrics {
  jev: EvalModeMetrics | null;
  llm: EvalModeMetrics | null;
  agreement_count: number | null;
  compared_count: number | null;
  agreement_rate: number | null;
  disagreement_case_ids: string[];
}

export interface EvalRunSummary {
  run_id: string;
  mode: string;
  created_at: string;
  case_count: number;
}

export interface EvalRunListResponse {
  runs: EvalRunSummary[];
}

export interface EvalRunView {
  run_id: string;
  mode: string;
  created_at: string;
  case_count: number;
  metrics: EvalComparisonMetrics;
  outcomes: EvalCaseOutcome[];
}

export interface PolicyThresholdView {
  confirmation: number;
  risk: number;
  reasoning: number;
  confidence: number;
  completion: number;
}

export interface ToolPolicyView {
  name: string;
  risk: string;
  description: string;
  requires_confirmation: boolean;
}

export interface PolicyView {
  thresholds: PolicyThresholdView;
  tools: ToolPolicyView[];
  confirmation_ttl_seconds: number;
  confirmation_binding: string;
}

/**
 * Transport types for the JevRouter API.
 *
 * This is a hand-written mirror of `apps/api/schemas.py`, not a generated
 * client. The API is the source of truth: when a field changes there, it has to
 * change here. Optionality matches the API — a field the store may return as
 * `NULL` is `| null` here, because an absent probability and a real `0.0` mean
 * different things and must not be rendered the same way.
 */

/** A run that has not reached a terminal status yet. */
export type LiveStatus = "running" | "awaiting_confirmation" | "awaiting_input";

/** The terminal statuses the core package's `RunStatus` can report. */
export type TerminalStatus =
  | "completed"
  | "needs_user_input"
  | "needs_confirmation"
  | "rejected"
  | "budget_exhausted"
  | "failed";

/**
 * Statuses are transported as plain strings, so an unrecognized value has to be
 * survivable rather than a type error at runtime.
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
 * One completed step, flattened from the core package's `StepTrace`.
 *
 * `arguments`, `result` and `state_snapshot` are JSON of a shape this layer does
 * not model, so they stay `unknown` and are rendered through a JSON viewer.
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
 * One case outcome from an eval run, mirrored from `apps/api/schemas.py`.
 *
 * The policy fields are `null` for the LLM baseline because it produces no
 * probabilities — an absent escalation and a real `false` are different facts
 * and must not render the same way.
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

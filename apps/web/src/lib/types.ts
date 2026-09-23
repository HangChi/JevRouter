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

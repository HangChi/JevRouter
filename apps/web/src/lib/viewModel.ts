import {
  COMPLETION_THRESHOLD,
  CONFIRMATION_THRESHOLD,
  QUALITY_LEVEL_COUNT,
  REASONING_THRESHOLD,
  RISK_LEVEL_COUNT,
  RISK_THRESHOLD,
  ROUTE_CONFIDENCE_THRESHOLD,
} from "./thresholds";
import type { EvalComparisonMetrics, EvalModeMetrics, EvalCaseOutcome, TraceView } from "./types";

/**
 * Pure view model over the API's transport types.
 *
 * Nothing here touches React, the network or the DOM: the components lay out
 * and style, and this module decides what a status means, which branch a step
 * took and whether a threshold was crossed. Keeping that split is what makes
 * the interesting logic testable without rendering anything.
 */

export type Tone = "neutral" | "live" | "blocked" | "good" | "bad";

/**
 * Which branch a step took, derived from the outcome plus what actually
 * happened. `executed` wins over everything: an approved action that ran is an
 * executed action, however it got there.
 */
export type Branch =
  | "executed"
  | "denied"
  | "approved_failed"
  | "rejected"
  | "delegated"
  | "asked"
  | "finished"
  | "not_executed"
  | "unknown";

/** Rendered wherever a field the API did not return would otherwise go. */
export const ABSENT = "—";

const LIVE_STATUSES = new Set(["running", "awaiting_confirmation", "awaiting_input"]);
const BLOCKED_STATUSES = new Set([
  "awaiting_confirmation",
  "awaiting_input",
  "needs_confirmation",
  "needs_user_input",
]);
const GOOD_STATUSES = new Set(["completed"]);
const BAD_STATUSES = new Set(["rejected", "budget_exhausted", "failed"]);

/**
 * Map a transported status to a presentation tone. Blocking states are checked
 * first so a live run that is waiting on a human reads as blocked rather than
 * merely live, and anything unrecognized falls through to `bad` instead of
 * being drawn as if it were fine.
 */
export function statusTone(status: string): Tone {
  if (BLOCKED_STATUSES.has(status)) {
    return "blocked";
  }
  if (LIVE_STATUSES.has(status)) {
    return "live";
  }
  if (GOOD_STATUSES.has(status)) {
    return "good";
  }
  if (BAD_STATUSES.has(status)) {
    return "bad";
  }
  return "bad";
}

/**
 * A run is live only while it is still going. The two terminal statuses that end
 * because a human was needed (`needs_confirmation`, `needs_user_input`) read as
 * blocked but are finished, so polling must stop for them too.
 */
export function isLiveStatus(status: string): boolean {
  return LIVE_STATUSES.has(status);
}

export function policyBranch(trace: TraceView): Branch {
  if (trace.executed) {
    return "executed";
  }
  if (trace.confirmed === false) {
    return "denied";
  }
  if (trace.confirmed === true) {
    // Approved but never executed: the tool was cleared to run and then failed.
    return "approved_failed";
  }
  switch (trace.policy_outcome) {
    case "reject":
      return "rejected";
    case "delegate_to_llm":
      return "delegated";
    case "ask_user":
      return "asked";
    case "finish":
      return "finished";
    case "execute":
    case "ask_confirmation":
      return "not_executed";
    default:
      return "unknown";
  }
}

export interface ProbabilityMeter {
  key: "route_confidence" | "requires_confirmation" | "needs_reasoning" | "completion_probability";
  label: string;
  value: number;
  threshold: number;
  /** Which side of the threshold the Policy Engine treats as the trigger. */
  direction: "above" | "below";
  /** Whether this signal is on the triggering side, using the policy's operators. */
  crossed: boolean;
}

/**
 * The three `noul` routing probabilities, which the client validates into
 * `[0, 1]`. The comparisons mirror `jev_router/policy.py`: confirmation and
 * reasoning trigger strictly above their thresholds, confidence triggers
 * strictly below its own.
 */
export function probabilityMeters(trace: TraceView): ProbabilityMeter[] {
  const meters: ProbabilityMeter[] = [];
  const push = (
    key: ProbabilityMeter["key"],
    label: string,
    value: number | null,
    threshold: number,
    direction: ProbabilityMeter["direction"],
  ) => {
    if (!isFiniteNumber(value)) {
      return;
    }
    meters.push({
      key,
      label,
      value,
      threshold,
      direction,
      crossed: direction === "above" ? value > threshold : value < threshold,
    });
  };

  push("route_confidence", "Route confidence", trace.route_confidence, ROUTE_CONFIDENCE_THRESHOLD, "below");
  push(
    "requires_confirmation",
    "Confirmation need",
    trace.requires_confirmation,
    CONFIRMATION_THRESHOLD,
    "above",
  );
  push("needs_reasoning", "Reasoning need", trace.needs_reasoning, REASONING_THRESHOLD, "above");
  return meters;
}

/**
 * The completion probability, measured against the Runner's own threshold. It is
 * kept apart from the routing meters because it comes from the Verifier, not the
 * Router, and is only present on a step that was verified.
 */
export function completionMeter(trace: TraceView): ProbabilityMeter | null {
  if (!isFiniteNumber(trace.completion_probability)) {
    return null;
  }
  return {
    key: "completion_probability",
    label: "Completion",
    value: trace.completion_probability,
    threshold: COMPLETION_THRESHOLD,
    direction: "below",
    crossed: trace.completion_probability < COMPLETION_THRESHOLD,
  };
}

export interface ScoreReadout {
  key: "route_risk" | "quality_score";
  label: string;
  value: number;
  /** `null` for a score no threshold is defined against. */
  threshold: number | null;
  level: number;
  levelCount: number;
  crossed: boolean;
}

/**
 * The two provider scores. `ScoreAnswer.score` is a finite float the core
 * package does not normalize, so these are reported as numbers with their
 * thresholds and a level strip, never as 0–1 meters.
 */
export function scoreReadouts(trace: TraceView): ScoreReadout[] {
  const readouts: ScoreReadout[] = [];
  if (isFiniteNumber(trace.route_risk)) {
    readouts.push({
      key: "route_risk",
      label: "Route risk",
      value: trace.route_risk,
      threshold: RISK_THRESHOLD,
      level: levelOf(trace.route_risk, RISK_LEVEL_COUNT),
      levelCount: RISK_LEVEL_COUNT,
      crossed: trace.route_risk >= RISK_THRESHOLD,
    });
  }
  if (isFiniteNumber(trace.quality_score)) {
    readouts.push({
      key: "quality_score",
      label: "Result quality",
      value: trace.quality_score,
      threshold: null,
      level: levelOf(trace.quality_score, QUALITY_LEVEL_COUNT),
      levelCount: QUALITY_LEVEL_COUNT,
      crossed: false,
    });
  }
  return readouts;
}

export interface VerificationReadout {
  completionProbability: number;
  completionThreshold: number;
  /** The Runner completes at `>=` its threshold. */
  completionMet: boolean;
  qualityScore: number;
  qualityLevel: number;
  qualityLevelCount: number;
}

/** A step carries a verification only when the Verifier ran for it. */
export function verificationReadout(trace: TraceView): VerificationReadout | null {
  if (!isFiniteNumber(trace.completion_probability) || !isFiniteNumber(trace.quality_score)) {
    return null;
  }
  return {
    completionProbability: trace.completion_probability,
    completionThreshold: COMPLETION_THRESHOLD,
    completionMet: trace.completion_probability >= COMPLETION_THRESHOLD,
    qualityScore: trace.quality_score,
    qualityLevel: levelOf(trace.quality_score, QUALITY_LEVEL_COUNT),
    qualityLevelCount: QUALITY_LEVEL_COUNT,
  };
}

export interface ChainNode {
  step: number;
  action: string;
  outcome: string | null;
  branch: Branch;
}

/** One node per step, in step order, for the run-level decision chain. */
export function decisionChain(traces: TraceView[]): ChainNode[] {
  return [...traces]
    .sort((left, right) => left.step - right.step)
    .map((trace) => ({
      step: trace.step,
      action: trace.action,
      outcome: trace.policy_outcome,
      branch: policyBranch(trace),
    }));
}

const BRANCH_LABELS: Record<Branch, string> = {
  executed: "Executed",
  denied: "Confirmation denied",
  approved_failed: "Approved, then failed",
  rejected: "Rejected",
  delegated: "Delegated to LLM",
  asked: "Asked the user",
  finished: "Finished",
  not_executed: "Not executed",
  unknown: "Unknown",
};

const OUTCOME_LABELS: Record<string, string> = {
  execute: "Execute",
  ask_confirmation: "Ask confirmation",
  delegate_to_llm: "Delegate to LLM",
  ask_user: "Ask user",
  finish: "Finish",
  reject: "Reject",
};

export function branchLabel(branch: Branch): string {
  return BRANCH_LABELS[branch];
}

/** The policy outcome verbatim when it is known, so nothing is reworded. */
export function outcomeLabel(outcome: string | null): string {
  if (outcome === null) {
    return ABSENT;
  }
  return OUTCOME_LABELS[outcome] ?? outcome;
}

/** Tone per policy outcome, used for the chain and the step headers. */
export function outcomeTone(outcome: string | null): Tone {
  switch (outcome) {
    case "finish":
      return "good";
    case "ask_confirmation":
    case "ask_user":
      return "blocked";
    case "execute":
    case "delegate_to_llm":
      return "neutral";
    case "reject":
      return "bad";
    default:
      return "bad";
  }
}

export function formatDuration(durationMs: number): string {
  if (!isFiniteNumber(durationMs) || durationMs < 0) {
    return ABSENT;
  }
  const rounded = Math.round(durationMs);
  if (rounded < 1000) {
    return `${rounded} ms`;
  }
  return `${(durationMs / 1000).toFixed(2)} s`;
}

export function formatProbability(value: number | null): string {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(1)}%` : ABSENT;
}

export function formatScore(value: number | null): string {
  return isFiniteNumber(value) ? value.toFixed(2) : ABSENT;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** A 0-based index across `levelCount` levels, clamped so an odd score stays drawable. */
function levelOf(score: number, levelCount: number): number {
  return Math.min(Math.max(Math.round(score), 0), levelCount - 1);
}

/** Which router a metric belongs to, for labelling cards and table columns. */
export type EvalMode = "jev" | "llm";

/** A rate the mode cannot produce, rendered as absent rather than zero. */
export const ABSENT_RATE = ABSENT;

export interface MetricCard {
  key: string;
  label: string;
  value: string;
  /** A short explanation of what the number counts, shown under the value. */
  detail: string;
  tone: Tone;
}

export interface ModeCardSet {
  mode: EvalMode;
  label: string;
  cards: MetricCard[];
}

/**
 * The aggregate cards for one mode.
 *
 * Every count is shown next to the case count it is a share of, because "88%"
 * hides whether that is 44 of 50 or 4 of 5. Metrics a mode cannot produce — the
 * baseline has no policy outcome — are left out rather than shown as zero.
 */
export function modeCardSet(metrics: EvalModeMetrics): ModeCardSet {
  const total = metrics.case_count;
  const cards: MetricCard[] = [
    {
      key: "expected",
      label: "Expected match",
      value: formatRate(metrics.expected_match_rate),
      detail: `${metrics.expected_match_count} of ${total} chose the expected action`,
      tone: rateTone(metrics.expected_match_rate),
    },
    {
      key: "allowed",
      label: "Allowed match",
      value: formatRate(metrics.allowed_match_rate),
      detail: `${metrics.allowed_match_count} of ${total} chose an acceptable action`,
      tone: rateTone(metrics.allowed_match_rate),
    },
    {
      key: "success",
      label: "Success",
      value: formatRate(metrics.success_rate),
      // The baseline has no policy outcome, so confirmation is not part of what
      // it can succeed at; saying so would describe a fact it cannot have.
      detail:
        metrics.confirmation_match_count === null
          ? `${metrics.success_count} of ${total} chose an acceptable action`
          : `${metrics.success_count} of ${total} matched and confirmed as the case required`,
      tone: rateTone(metrics.success_rate),
    },
    {
      key: "latency",
      label: "Latency",
      value: formatDuration(metrics.latency.mean_ms),
      detail: `p50 ${formatDuration(metrics.latency.p50_ms)} · p95 ${formatDuration(
        metrics.latency.p95_ms,
      )} · max ${formatDuration(metrics.latency.max_ms)}`,
      tone: "neutral",
    },
    {
      key: "tokens",
      label: "Tokens",
      value: formatTokens(metrics.input_tokens?.mean ?? null, metrics.output_tokens?.mean ?? null),
      detail:
        metrics.input_tokens === null || metrics.output_tokens === null
          ? "the provider reported no usage"
          : `in ${metrics.input_tokens.total} · out ${metrics.output_tokens.total} across ${total} cases`,
      tone: "neutral",
    },
  ];

  if (metrics.escalation_rate !== null && metrics.escalation_count !== null) {
    cards.push({
      key: "escalated",
      label: "Escalated",
      value: formatRate(metrics.escalation_rate),
      detail: `${metrics.escalation_count} of ${total} stopped automatic execution`,
      tone: "neutral",
    });
  }
  if (
    metrics.confirmation_requested_count !== null &&
    metrics.confirmation_match_count !== null
  ) {
    cards.push({
      key: "confirmation",
      label: "Confirmation fit",
      value: formatRate(metrics.confirmation_match_count / total),
      detail: `${metrics.confirmation_requested_count} asked · ${metrics.confirmation_match_count} of ${total} matched the case`,
      tone: rateTone(metrics.confirmation_match_count / total),
    });
  }
  if (metrics.error_count > 0) {
    cards.push({
      key: "errors",
      label: "Errors",
      value: formatRate(metrics.error_rate),
      detail: `${metrics.error_count} of ${total} cases errored`,
      tone: "bad",
    });
  }

  return {
    mode: metrics.mode === "llm" ? "llm" : "jev",
    label: metrics.mode === "llm" ? "LLM baseline" : "Jev",
    cards,
  };
}

/** The card sets a run can show, Jev first because it is the subject. */
export function comparisonCardSets(metrics: EvalComparisonMetrics): ModeCardSet[] {
  const sets: ModeCardSet[] = [];
  if (metrics.jev !== null) {
    sets.push(modeCardSet(metrics.jev));
  }
  if (metrics.llm !== null) {
    sets.push(modeCardSet(metrics.llm));
  }
  return sets;
}

export interface AgreementCard {
  key: "agreement";
  label: "Routing agreement";
  value: string;
  detail: string;
  tone: Tone;
}

/**
 * How often the two routers named the same action. It is absent unless both
 * routers answered at least one case: "0%" and "never compared" are different
 * statements, and only one of them is a finding.
 */
export function agreementCard(metrics: EvalComparisonMetrics): AgreementCard | null {
  if (metrics.agreement_rate === null || metrics.compared_count === null) {
    return null;
  }
  const compared = metrics.compared_count;
  const agreed = metrics.agreement_count ?? 0;
  return {
    key: "agreement",
    label: "Routing agreement",
    value: formatRate(metrics.agreement_rate),
    detail: `${agreed} of ${compared} compared cases named the same action`,
    tone: rateTone(metrics.agreement_rate),
  };
}

export interface ComparisonRow {
  caseId: string;
  goal: string;
  expectedAction: string;
  jev: EvalCaseOutcome | null;
  llm: EvalCaseOutcome | null;
  agreed: boolean | null;
}

/**
 * One row per case, pairing both routers' outcomes.
 *
 * Outcomes arrive ordered by `(case_id, mode)`, so a single pass pairs them.
 * `agreed` stays `null` when either side never answered: a router error is not a
 * disagreement, and counting it as one would understate the agreement rate.
 */
export function comparisonRows(outcomes: EvalCaseOutcome[]): ComparisonRow[] {
  const byCase = new Map<string, { jev?: EvalCaseOutcome; llm?: EvalCaseOutcome }>();
  for (const outcome of outcomes) {
    const entry = byCase.get(outcome.case_id) ?? {};
    if (outcome.mode === "llm") {
      entry.llm = outcome;
    } else {
      entry.jev = outcome;
    }
    byCase.set(outcome.case_id, entry);
  }
  return [...byCase.entries()].map(([caseId, entry]) => {
    const jev = entry.jev ?? null;
    const llm = entry.llm ?? null;
    const agreed =
      jev !== null && llm !== null && jev.action !== null && llm.action !== null
        ? jev.action === llm.action
        : null;
    const reference = jev ?? llm;
    return {
      caseId,
      goal: reference?.goal ?? "",
      expectedAction: reference?.expected_action ?? ABSENT,
      jev,
      llm,
      agreed,
    };
  });
}

/** The action a router reported, or the error that replaced it. */
export function outcomeAction(outcome: EvalCaseOutcome | null): string {
  if (outcome === null) {
    return ABSENT;
  }
  if (outcome.action !== null) {
    return outcome.action;
  }
  return outcome.error === null ? ABSENT : `error: ${outcome.error}`;
}

export function formatRate(value: number | null): string {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(1)}%` : ABSENT;
}

export function formatTokens(input: number | null, output: number | null): string {
  if (!isFiniteNumber(input) || !isFiniteNumber(output)) {
    return ABSENT;
  }
  return `${input} / ${output}`;
}

/** Tone for a rate: higher is better, and the bands are deliberately coarse. */
export function rateTone(value: number | null): Tone {
  if (!isFiniteNumber(value)) {
    return "neutral";
  }
  if (value >= 0.9) {
    return "good";
  }
  if (value >= 0.7) {
    return "neutral";
  }
  return "bad";
}

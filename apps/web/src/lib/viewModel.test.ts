import { describe, expect, it } from "vitest";

import {
  ABSENT,
  branchLabel,
  completionMeter,
  decisionChain,
  formatDuration,
  formatProbability,
  formatScore,
  isLiveStatus,
  outcomeLabel,
  outcomeTone,
  policyBranch,
  probabilityMeters,
  scoreReadouts,
  statusTone,
  verificationReadout,
} from "./viewModel";
import type { TraceView } from "./types";

function trace(overrides: Partial<TraceView> = {}): TraceView {
  return {
    step: 0,
    action: "calculator",
    policy_outcome: "execute",
    policy_reason: "The registered action is permitted by the configured thresholds.",
    executed: true,
    result: { value: 4 },
    route_confidence: 0.9,
    route_risk: 1,
    requires_confirmation: 0.1,
    needs_reasoning: 0.2,
    confirmed: null,
    arguments: { expression: "2 + 2" },
    completion_probability: 0.8,
    quality_score: 3,
    state_snapshot: { goal: "add two numbers" },
    duration_ms: 120,
    ...overrides,
  };
}

describe("statusTone", () => {
  it("treats a run waiting on a human as blocked, not merely live", () => {
    expect(statusTone("awaiting_confirmation")).toBe("blocked");
    expect(statusTone("awaiting_input")).toBe("blocked");
    expect(statusTone("needs_confirmation")).toBe("blocked");
    expect(statusTone("needs_user_input")).toBe("blocked");
  });

  it("separates a running run from a completed one", () => {
    expect(statusTone("running")).toBe("live");
    expect(statusTone("completed")).toBe("good");
  });

  it("treats the failure statuses as bad", () => {
    expect(statusTone("rejected")).toBe("bad");
    expect(statusTone("budget_exhausted")).toBe("bad");
    expect(statusTone("failed")).toBe("bad");
  });

  it("never renders an unknown status as if it were fine", () => {
    expect(statusTone("something_new")).toBe("bad");
    expect(statusTone("")).toBe("bad");
  });
});

describe("isLiveStatus", () => {
  it("covers the three live states only", () => {
    expect(isLiveStatus("running")).toBe(true);
    expect(isLiveStatus("awaiting_confirmation")).toBe(true);
    expect(isLiveStatus("awaiting_input")).toBe(true);
  });

  it("stops polling at a terminal status, including the blocked ones", () => {
    expect(isLiveStatus("completed")).toBe(false);
    expect(isLiveStatus("failed")).toBe(false);
    expect(isLiveStatus("needs_confirmation")).toBe(false);
    expect(isLiveStatus("needs_user_input")).toBe(false);
  });
});

describe("policyBranch", () => {
  it("reports an executed step as executed even when it was confirmed", () => {
    expect(policyBranch(trace({ confirmed: true }))).toBe("executed");
  });

  it("separates a denied confirmation from a step that never ran", () => {
    expect(policyBranch(trace({ executed: false, confirmed: false }))).toBe("denied");
    expect(policyBranch(trace({ executed: false, confirmed: null }))).toBe("not_executed");
  });

  it("distinguishes an approved action that then failed", () => {
    expect(policyBranch(trace({ executed: false, confirmed: true }))).toBe("approved_failed");
  });

  it("maps each control outcome to its branch", () => {
    const base = { executed: false, confirmed: null };
    expect(policyBranch(trace({ ...base, policy_outcome: "reject" }))).toBe("rejected");
    expect(policyBranch(trace({ ...base, policy_outcome: "delegate_to_llm" }))).toBe("delegated");
    expect(policyBranch(trace({ ...base, policy_outcome: "ask_user" }))).toBe("asked");
    expect(policyBranch(trace({ ...base, policy_outcome: "finish" }))).toBe("finished");
    expect(policyBranch(trace({ ...base, policy_outcome: "ask_confirmation" }))).toBe("not_executed");
  });

  it("does not guess at an outcome it does not know", () => {
    expect(policyBranch(trace({ executed: false, confirmed: null, policy_outcome: "later_thing" }))).toBe(
      "unknown",
    );
    expect(policyBranch(trace({ executed: false, confirmed: null, policy_outcome: null }))).toBe("unknown");
  });
});

describe("probabilityMeters", () => {
  it("uses the policy's strict comparisons", () => {
    const [confidence] = probabilityMeters(trace({ route_confidence: 0.75 }));
    expect(confidence.crossed).toBe(false);
    expect(probabilityMeters(trace({ route_confidence: 0.7499 }))[0].crossed).toBe(true);

    const [, confirmation] = probabilityMeters(trace({ requires_confirmation: 0.75 }));
    expect(confirmation.crossed).toBe(false);
    expect(probabilityMeters(trace({ requires_confirmation: 0.7501 }))[1].crossed).toBe(true);
  });

  it("omits a signal the API did not return instead of drawing zero", () => {
    const meters = probabilityMeters(trace({ needs_reasoning: null }));
    expect(meters.map((meter) => meter.key)).toEqual(["route_confidence", "requires_confirmation"]);
  });
});

describe("scoreReadouts", () => {
  it("reports the raw score with its threshold and level", () => {
    const [risk] = scoreReadouts(trace({ route_risk: 2.5 }));
    expect(risk.value).toBe(2.5);
    expect(risk.threshold).toBe(2.5);
    expect(risk.level).toBe(3);
    expect(risk.levelCount).toBe(5);
    expect(risk.crossed).toBe(true);
  });

  it("crosses at the threshold, matching the policy's non-strict comparison", () => {
    expect(scoreReadouts(trace({ route_risk: 2.49 }))[0].crossed).toBe(false);
    expect(scoreReadouts(trace({ route_risk: 2.5 }))[0].crossed).toBe(true);
  });

  it("gives the quality score no threshold", () => {
    const readouts = scoreReadouts(trace({ quality_score: 3 }));
    const quality = readouts.find((readout) => readout.key === "quality_score");
    expect(quality?.threshold).toBeNull();
    expect(quality?.level).toBe(3);
    expect(quality?.levelCount).toBe(4);
  });

  it("clamps a level for a score outside the assumed scale", () => {
    expect(scoreReadouts(trace({ route_risk: 99 }))[0].level).toBe(4);
    expect(scoreReadouts(trace({ route_risk: -5 }))[0].level).toBe(0);
  });
});

describe("verificationReadout", () => {
  it("is absent when the verifier did not run for the step", () => {
    expect(verificationReadout(trace({ completion_probability: null, quality_score: null }))).toBeNull();
  });

  it("uses the runner's non-strict completion comparison", () => {
    expect(verificationReadout(trace({ completion_probability: 0.75 }))?.completionMet).toBe(true);
    expect(verificationReadout(trace({ completion_probability: 0.7499 }))?.completionMet).toBe(false);
  });
});

describe("completionMeter", () => {
  it("crosses below the runner's threshold", () => {
    expect(completionMeter(trace({ completion_probability: 0.75 }))?.crossed).toBe(false);
    expect(completionMeter(trace({ completion_probability: 0.5 }))?.crossed).toBe(true);
  });

  it("is absent for a step that was never verified", () => {
    expect(completionMeter(trace({ completion_probability: null }))).toBeNull();
  });
});

describe("decisionChain", () => {
  it("returns one node per step in step order", () => {
    const chain = decisionChain([trace({ step: 2 }), trace({ step: 0 }), trace({ step: 1 })]);
    expect(chain.map((node) => node.step)).toEqual([0, 1, 2]);
    expect(chain[0].action).toBe("calculator");
    expect(chain[0].outcome).toBe("execute");
    expect(chain[0].branch).toBe("executed");
  });

  it("does not mutate the input", () => {
    const traces = [trace({ step: 1 }), trace({ step: 0 })];
    decisionChain(traces);
    expect(traces.map((entry) => entry.step)).toEqual([1, 0]);
  });
});

describe("labels and tones", () => {
  it("labels every branch", () => {
    expect(branchLabel("denied")).toBe("确认被拒绝");
    expect(branchLabel("approved_failed")).toBe("已批准但执行失败");
  });

  it("translates a known outcome and leaves an unknown one intact", () => {
    expect(outcomeLabel("execute")).toBe("执行");
    expect(outcomeLabel("later_thing")).toBe("later_thing");
    expect(outcomeLabel(null)).toBe(ABSENT);
  });

  it("tones a control outcome as blocked and a rejection as bad", () => {
    expect(outcomeTone("ask_confirmation")).toBe("blocked");
    expect(outcomeTone("ask_user")).toBe("blocked");
    expect(outcomeTone("reject")).toBe("bad");
    expect(outcomeTone("finish")).toBe("good");
    expect(outcomeTone("execute")).toBe("neutral");
    expect(outcomeTone(null)).toBe("bad");
  });
});

describe("formatters", () => {
  it("formats durations below and above a second", () => {
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(842)).toBe("842 ms");
    expect(formatDuration(999.6)).toBe("1.00 s");
    expect(formatDuration(1234)).toBe("1.23 s");
  });

  it("renders an absent value as a dash rather than zero", () => {
    expect(formatProbability(null)).toBe(ABSENT);
    expect(formatProbability(0)).toBe("0.0%");
    expect(formatScore(null)).toBe(ABSENT);
    expect(formatScore(2.5)).toBe("2.50");
  });

  it("does not render a non-finite number", () => {
    expect(formatProbability(Number.NaN)).toBe(ABSENT);
    expect(formatScore(Number.POSITIVE_INFINITY)).toBe(ABSENT);
    expect(formatDuration(-1)).toBe(ABSENT);
  });
});

import {
  ABSENT as EVAL_ABSENT,
  agreementCard,
  comparisonCardSets,
  comparisonRows,
  formatRate,
  formatTokens,
  modeCardSet,
  outcomeAction,
  rateTone,
} from "./viewModel";
import type { EvalCaseOutcome, EvalComparisonMetrics, EvalModeMetrics } from "./types";

function jevMetrics(overrides: Partial<EvalModeMetrics> = {}): EvalModeMetrics {
  return {
    mode: "jev",
    case_count: 50,
    error_count: 0,
    expected_match_count: 44,
    allowed_match_count: 47,
    success_count: 41,
    escalation_count: 4,
    confirmation_expected_count: 17,
    confirmation_requested_count: 15,
    confirmation_match_count: 45,
    expected_match_rate: 0.88,
    allowed_match_rate: 0.94,
    success_rate: 0.82,
    error_rate: 0,
    escalation_rate: 0.08,
    latency: { mean_ms: 118.4, p50_ms: 104, p95_ms: 210, max_ms: 402 },
    input_tokens: { mean: 423.2, total: 21160 },
    output_tokens: { mean: 12.1, total: 605 },
    ...overrides,
  };
}

function llmMetrics(overrides: Partial<EvalModeMetrics> = {}): EvalModeMetrics {
  return {
    mode: "llm",
    case_count: 50,
    error_count: 0,
    expected_match_count: 41,
    allowed_match_count: 45,
    success_count: 41,
    escalation_count: null,
    confirmation_expected_count: null,
    confirmation_requested_count: null,
    confirmation_match_count: null,
    expected_match_rate: 0.82,
    allowed_match_rate: 0.9,
    success_rate: 0.82,
    error_rate: 0,
    escalation_rate: null,
    latency: { mean_ms: 1642.7, p50_ms: 1500, p95_ms: 2800, max_ms: 3900 },
    input_tokens: { mean: 612.4, total: 30620 },
    output_tokens: { mean: 97.3, total: 4865 },
    ...overrides,
  };
}

function comparison(overrides: Partial<EvalComparisonMetrics> = {}): EvalComparisonMetrics {
  return {
    jev: jevMetrics(),
    llm: llmMetrics(),
    agreement_count: 46,
    compared_count: 50,
    agreement_rate: 0.92,
    disagreement_case_ids: ["case-3", "case-17", "case-31", "case-44"],
    ...overrides,
  };
}

function outcome(overrides: Partial<EvalCaseOutcome> = {}): EvalCaseOutcome {
  return {
    case_id: "case-1",
    goal: "what is 2 + 2?",
    expected_action: "calculator",
    allowed_actions: ["calculator"],
    requires_confirmation: false,
    mode: "jev",
    action: "calculator",
    matched_expected: true,
    matched_allowed: true,
    succeeded: true,
    policy_outcome: "execute",
    escalated: false,
    confirmation_requested: false,
    latency_ms: 104,
    input_tokens: 10,
    output_tokens: 5,
    error: null,
    ...overrides,
  };
}

describe("modeCardSet", () => {
  it("shows every count next to the case count it is a share of", () => {
    const cards = modeCardSet(jevMetrics()).cards;
    const expected = cards.find((card) => card.key === "expected");
    expect(expected?.value).toBe("88.0%");
    expect(expected?.detail).toBe("44/50 选择了期望动作");
    expect(expected?.tone).toBe("neutral");
  });

  it("formats latency with its percentiles and tokens with their totals", () => {
    const cards = modeCardSet(jevMetrics()).cards;
    expect(cards.find((card) => card.key === "latency")?.value).toBe("118 ms");
    expect(cards.find((card) => card.key === "latency")?.detail).toBe(
      "p50 104 ms · p95 210 ms · 最大 402 ms",
    );
    expect(cards.find((card) => card.key === "tokens")?.value).toBe("423.2 / 12.1");
    expect(cards.find((card) => card.key === "tokens")?.detail).toBe(
      "入 21160 · 出 605，共 50 个用例",
    );
  });

  it("omits the policy cards the LLM baseline cannot produce", () => {
    const keys = modeCardSet(llmMetrics()).cards.map((card) => card.key);
    expect(keys).not.toContain("escalated");
    expect(keys).not.toContain("confirmation");
    expect(keys).toContain("expected");
  });

  it("describes the baseline's success without confirmation wording", () => {
    const baseline = modeCardSet(llmMetrics()).cards.find((card) => card.key === "success");
    expect(baseline?.detail).toBe("41/50 选择了可接受动作");
    const jev = modeCardSet(jevMetrics()).cards.find((card) => card.key === "success");
    expect(jev?.detail).toBe("41/50 命中且确认结论与用例要求一致");
  });

  it("labels the baseline as the baseline", () => {
    expect(modeCardSet(llmMetrics()).label).toBe("LLM 基线");
    expect(modeCardSet(jevMetrics()).label).toBe("Jev");
  });

  it("adds an error card only when cases errored", () => {
    expect(modeCardSet(jevMetrics()).cards.map((card) => card.key)).not.toContain("errors");
    const withErrors = modeCardSet(jevMetrics({ error_count: 3, error_rate: 0.06 })).cards;
    expect(withErrors.find((card) => card.key === "errors")?.detail).toBe("3/50 个用例出错");
  });

  it("reports absent token usage rather than zeros", () => {
    const cards = modeCardSet(
      jevMetrics({ input_tokens: null, output_tokens: null }),
    ).cards;
    expect(cards.find((card) => card.key === "tokens")?.value).toBe(EVAL_ABSENT);
    expect(cards.find((card) => card.key === "tokens")?.detail).toBe("提供方未返回用量");
  });
});

describe("comparisonCardSets", () => {
  it("lists Jev first and skips a mode the run did not use", () => {
    expect(comparisonCardSets(comparison()).map((set) => set.mode)).toEqual(["jev", "llm"]);
    expect(comparisonCardSets(comparison({ llm: null })).map((set) => set.mode)).toEqual(["jev"]);
    expect(comparisonCardSets(comparison({ jev: null, llm: null }))).toEqual([]);
  });
});

describe("agreementCard", () => {
  it("reports the paired count and the shared actions", () => {
    const card = agreementCard(comparison());
    expect(card?.value).toBe("92.0%");
    expect(card?.detail).toBe("46/50 个可比用例选择了相同动作");
    expect(card?.tone).toBe("good");
  });

  it("is absent when the two routers were never compared", () => {
    expect(agreementCard(comparison({ agreement_rate: null, compared_count: null }))).toBeNull();
  });

  it("distinguishes a real zero from never compared", () => {
    expect(agreementCard(comparison({ agreement_rate: 0, agreement_count: 0 }))?.value).toBe("0.0%");
  });
});

describe("comparisonRows", () => {
  it("pairs both routers per case in case order", () => {
    const rows = comparisonRows([
      outcome({ case_id: "case-1", mode: "jev" }),
      outcome({ case_id: "case-1", mode: "llm", action: "web_search", policy_outcome: null }),
      outcome({ case_id: "case-2", mode: "jev" }),
      outcome({ case_id: "case-2", mode: "llm", action: "calculator", policy_outcome: null }),
    ]);
    expect(rows.map((row) => row.caseId)).toEqual(["case-1", "case-2"]);
    expect(rows[0].agreed).toBe(false);
    expect(rows[1].agreed).toBe(true);
    expect(rows[0].expectedAction).toBe("calculator");
  });

  it("does not count a router error as a disagreement", () => {
    const rows = comparisonRows([
      outcome({ case_id: "case-1", mode: "jev", action: null, error: "http: down" }),
      outcome({ case_id: "case-1", mode: "llm", action: "calculator", policy_outcome: null }),
    ]);
    expect(rows[0].agreed).toBeNull();
  });

  it("renders a one-sided run with the missing side absent", () => {
    const rows = comparisonRows([outcome({ mode: "jev" })]);
    expect(rows[0].jev?.action).toBe("calculator");
    expect(rows[0].llm).toBeNull();
    expect(outcomeAction(rows[0].llm)).toBe(EVAL_ABSENT);
  });
});

describe("outcomeAction", () => {
  it("shows the action, or the error that replaced it", () => {
    expect(outcomeAction(outcome())).toBe("calculator");
    expect(outcomeAction(outcome({ action: null, error: "http: provider down" }))).toBe(
      "出错：http: provider down",
    );
    expect(outcomeAction(outcome({ action: null, error: null }))).toBe(EVAL_ABSENT);
    expect(outcomeAction(null)).toBe(EVAL_ABSENT);
  });
});

describe("eval formatters", () => {
  it("formats rates and keeps an absent rate absent", () => {
    expect(formatRate(0.88)).toBe("88.0%");
    expect(formatRate(0)).toBe("0.0%");
    expect(formatRate(null)).toBe(EVAL_ABSENT);
  });

  it("formats a token pair", () => {
    expect(formatTokens(423, 12)).toBe("423 / 12");
    expect(formatTokens(null, 12)).toBe(EVAL_ABSENT);
  });

  it("tones a rate by coarse bands", () => {
    expect(rateTone(0.95)).toBe("good");
    expect(rateTone(0.8)).toBe("neutral");
    expect(rateTone(0.4)).toBe("bad");
    expect(rateTone(null)).toBe("neutral");
  });
});

describe("formatTokens precision", () => {
  it("rounds a mean to one decimal instead of printing the arithmetic", () => {
    expect(formatTokens(207.97826086956522, 265.0217394348)).toBe("208 / 265");
    expect(formatTokens(606.56, 133.8)).toBe("606.6 / 133.8");
    expect(formatTokens(10, 5)).toBe("10 / 5");
  });
});

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
    expect(branchLabel("denied")).toBe("Confirmation denied");
    expect(branchLabel("approved_failed")).toBe("Approved, then failed");
  });

  it("keeps an unknown outcome verbatim instead of reworded", () => {
    expect(outcomeLabel("execute")).toBe("Execute");
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

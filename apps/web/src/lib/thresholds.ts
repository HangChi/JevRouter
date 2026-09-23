/**
 * Display-only mirror of the thresholds in `jev_router/policy.py` and the
 * Runner's completion threshold.
 *
 * These constants exist to draw marks on meters. The decision the dashboard
 * reports is always the API's `policy_outcome`; if a value here drifts from the
 * core package, the marks are wrong but the reported outcome is still right.
 * That is why they live in one module: the drift has one place to be fixed.
 */

/** Route confidence below this is delegated to the LLM. */
export const ROUTE_CONFIDENCE_THRESHOLD = 0.75;

/** A confirmation probability above this asks the user to confirm. */
export const CONFIRMATION_THRESHOLD = 0.75;

/** A reasoning need above this delegates the step to the LLM. */
export const REASONING_THRESHOLD = 0.7;

/** A risk score at or above this asks the user to confirm. */
export const RISK_THRESHOLD = 2.5;

/** The Runner's completion threshold for a finished task. */
export const COMPLETION_THRESHOLD = 0.75;

/**
 * Level counts for the two provider scores the dashboard renders. `route_risk`
 * is scored over the five risk levels the Router submits; `quality_score` over
 * the verifier's four-level legend. The core package does not normalize the
 * provider's score field, so these counts are an assumption about a 0-based
 * index scale — the raw number is always rendered next to the strip.
 */
export const RISK_LEVEL_COUNT = 5;
export const QUALITY_LEVEL_COUNT = 4;

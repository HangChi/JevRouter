# Feature Specification: Eval Runner and LLM Baseline

**Feature Branch**: `011-eval-runner`
**Status**: Complete

## Goal

Turn the MVP thresholds from guesses into measurements. A fixed, versioned set of routing cases is replayed against the Jev router and against an LLM baseline router, and the run produces routing agreement, expected/allowed match, escalation, confirmation and latency/token metrics. This phase adds no agent behaviour to the run path: the Runner, Policy Engine and tools are used exactly as they are, and the only core additions are the provider adapters the comparison needs.

## Background

`doc.md` orders the work so that the eval runner and the comparison dashboard come last, after the agent loop, trace persistence, HTTP boundary and web dashboard exist. `docs/development.md` already records the intent: "Eval：使用固定、版本化用例记录正确动作、允许动作集合和必要确认；分别统计路由一致率、任务完成率、升级率及延迟。" The thresholds in `jev_router/policy.py` are documented as initial project values that should be calibrated against evals; until this phase there is nothing to calibrate them against.

## Scope

In scope:

- `jev_router/clients/llm.py`: an httpx-based LLM adapter (Anthropic Messages API shape) with its own config and error taxonomy, mirroring how `clients/jev.py` isolates the Jev provider.
- `evals/`: a versioned case file, a case loader with validation, a deterministic tool registry, the LLM baseline router, the runner, the metrics aggregation and a CLI.
- Additive token-usage fields on `RouteDecision`, because the comparison table cannot show input/output tokens otherwise.
- Optional, settings-gated LLM delegation in `apps/api`, so `delegate_to_llm` stops being unconditionally fail-closed when an LLM is configured. Without LLM configuration the behaviour is exactly what phase 7 shipped.

Out of scope (phase 12):

- Persisting eval runs, the `POST/GET /evals` endpoints and the dashboard pages that render the comparison.
- Any change to the thresholds themselves. This phase measures; it does not calibrate.

## User Stories

### US1 - Replay a fixed case set offline

As the project owner, I need the case set to be a versioned file with the correct action, the acceptable action set and whether confirmation is necessary, so a run is reproducible and a case change is visible in review.

Acceptance scenarios:

1. `evals/cases.json` carries a `version` envelope and at least 50 cases covering every registered tool and all three control actions.
2. The loader refuses an unknown payload version, a duplicate case id, an empty case list, and a case whose expected action is outside its allowed set.
3. Every case is valid against the loader when the suite runs, so the committed file cannot rot silently.

### US2 - Measure Jev routing against expectations

As the project owner, I need per-case outcomes for the Jev router — chosen action, policy outcome, latency and token usage — so I can see where the router and the policy disagree with the case's expectation.

Acceptance scenarios:

1. Each case produces exactly one outcome per mode, with `matched_expected`, `matched_allowed`, `escalated`, `confirmation_requested` and `succeeded`.
2. A provider failure becomes an outcome carrying the error, not an exception that aborts the run.
3. `succeeded` requires the action to be acceptable **and** the policy's confirmation decision to match the case's `requires_confirmation`.

### US3 - Compare against an LLM baseline

As the project owner, I need the same cases routed by an LLM that sees the same goal, history and candidate actions, so the comparison is like-for-like.

Acceptance scenarios:

1. The baseline asks for a strict JSON object naming one candidate action; anything unparseable or outside the candidate set is an error outcome, not a silent default.
2. Each baseline outcome records latency and input/output tokens.
3. `compare` mode runs both routers per case and records agreement per case.

### US4 - Aggregate into stable metrics

As the project owner, I need aggregate metrics — match rates, escalation and confirmation rates, latency statistics and token statistics, plus the Jev/LLM agreement rate — so a threshold change can be judged by numbers instead of anecdotes.

Acceptance scenarios:

1. Metrics are computed by pure functions over the per-case outcomes, with no I/O.
2. Latency reports mean, p50, p95 and max in milliseconds; tokens report mean and total.
3. An empty outcome set yields zeroed metrics rather than a division by zero.

### US5 - Run it from the command line

As the project owner, I need a CLI that runs a mode against the real providers with explicit credentials, prints a summary and optionally writes a versioned JSON report, so an eval run is a deliberate, auditable act and not something a test does by accident.

Acceptance scenarios:

1. `python -m evals --mode jev|llm|compare` runs the selected routers; missing credentials fail before any case runs.
2. `--json-out PATH` writes the report; the summary prints to stdout either way.
3. The exit code is non-zero when any case errored, so a broken provider run cannot look like a clean one.

## Non-Goals

- No automatic threshold tuning, no statistical significance testing, no multi-run variance.
- No real web search or email: the eval registry uses the same offline tools the API uses, because the eval measures routing, not tool I/O.
- No browser surface (phase 12), no database writes (phase 12).

## Dependencies

- Phases 1–10: the client, tools, router, policy, state, verifier, runner, trace store, HTTP boundary and dashboard this phase measures and extends.

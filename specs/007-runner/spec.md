# Feature Specification: Bounded Runner

**Feature Branch**: `007-runner`
**Status**: Complete

## Goal

Assemble the Router, Policy Engine, TaskState/budget, and Verifier into one bounded `route → policy → execute → verify` loop. The Runner owns budget consumption and termination, and collapses every failure mode into a diagnosable terminal status instead of letting exceptions escape.

## User Stories

### US1 - Run a goal to completion

As an application developer, I need a single call that drives a task from a goal to a verified result so the API layer does not have to re-implement orchestration.

Acceptance scenarios:
1. A goal whose first route recommends a registered tool completes when the verifier's completion probability reaches the configured threshold.
2. A completion probability below the threshold routes again against the advanced state.
3. A `finish` recommendation with no completed step stops as complete without issuing a verification request.
4. A `finish` recommendation after at least one step is confirmed by the verifier before stopping.

### US2 - Never exceed the execution budget

As an application developer, I need the loop to stop safely when steps or model calls run out so a misrouting provider cannot spin forever.

Acceptance scenarios:
1. Exhausted step or model-call budget stops the run with `budget_exhausted` before another provider request.
2. Each loop iteration consumes exactly one step; each route, verification and delegation consumes one model call.
3. A budget whose model-call allowance cannot cover one route plus one verify per step is rejected at construction.

### US3 - Obtain explicit approval before side effects

As an application developer, I need external and workspace-writing tools gated by an explicit approval even when the provider's probabilities look safe.

Acceptance scenarios:
1. A `write` or `external` risk tool requires confirmation regardless of the policy outcome.
2. The confirmation handler receives the resolved arguments, not just the action name.
3. Missing or denied confirmation stops the run with `needs_confirmation` and performs no side effect.

### US4 - Diagnose every stop

As an application developer, I need a typed trace for every step, including steps that stop before a decision, so failures are auditable.

Acceptance scenarios:
1. Each loop iteration emits one `StepTrace` with the routing payload, decision probabilities, policy result, execution result and duration.
2. Paths that stop before a decision still emit a trace, so `RunResult.traces` is never empty for a started run.
3. A trace sink that raises does not abort the run.

## Requirements

- **FR-001**: Provide an asynchronous `Runner` that assembles `Router`, `PolicyEngine` and `Verifier` from one injected `JevClient`, model identifier and `ToolRegistry`.
- **FR-002**: Consume one step per iteration and one model call per route, verification and delegation, rejecting exhausted budget before further provider I/O.
- **FR-003**: Return an immutable `RunResult` with a terminal `RunStatus`, final `TaskState`, remaining budget, traces and optional diagnostic.
- **FR-004**: Leave completion thresholds, tool execution, confirmation, user input and delegation to injected collaborators; the Runner never blocks on a human.
- **FR-005**: Require confirmation for `write` and `external` risk tools independently of the policy outcome, bound to the resolved arguments.
- **FR-006**: Fail closed when a required handler is absent: `needs_confirmation`, `needs_user_input` or `failed` as appropriate.
- **FR-007**: Convert provider errors, tool input errors and state rejection into `failed` with a diagnostic, never an escaping exception.
- **FR-008**: Stop with `failed` when the verifier reports no progress on an unchanged state, instead of re-routing an identical payload until the budget runs out.
- **FR-009**: Emit one immutable `StepTrace` per iteration and for pre-decision terminations.
- **FR-010**: Not mutate task state in place, execute unregistered actions, or bypass the Policy Engine.
- **FR-011**: Offline tests cover completion, continuation, finish, budget exhaustion, confirmation gating, delegation, user input, every failure mode, trace emission and immutability.

## Success Criteria

- A verified run consumes exactly one step and two model calls per executing iteration.
- No side effect occurs without confirmation for `write`/`external` tools.
- No exception escapes `Runner.run`; every stop carries a status and a diagnostic.
- Ruff, strict mypy, and the full offline test suite pass.

## Non-Goals

- LLM adapter implementation (`clients/llm.py`), model discovery, retries or client contract changes.
- Trace persistence, task storage, API or dashboard.
- Task identity or status fields on `TaskState`.
- Threshold calibration, monetary budgets or dynamic budget refill.

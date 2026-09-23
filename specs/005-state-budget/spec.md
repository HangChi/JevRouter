# Feature Specification: Task State and Budget

**Feature Branch**: `005-state-budget`
**Status**: Complete

## Goal

Define the immutable task state and finite execution budget needed by later runner and verifier phases. This phase supplies validated state transitions and budget accounting, but does not route, execute tools, call models, or persist tasks.

## User Stories

### US1 - Track task progress

As an application developer, I need a typed task state containing the goal, current step, context, history, and latest result so each later decision can be grounded in the current task.

Acceptance scenarios:
1. A new task starts at step zero with its supplied goal and optional context.
2. Advancing a task returns a new state with exactly one additional step and updated history/result.
3. Existing state and nested input data are not mutated by a transition.
4. Empty goals and invalid step counts are rejected.

### US2 - Bound work

As an application developer, I need finite step and model-call budgets so a later agent loop can stop deterministically instead of running without bound.

Acceptance scenarios:
1. A budget accepts finite non-negative limits and starts with all limits remaining.
2. Consuming an available step or model call returns a new budget with the corresponding counter reduced by one.
3. Exhausted budgets reject further consumption without changing the original budget.
4. Zero limits are valid and immediately exhausted.

## Requirements

- **FR-001**: Provide immutable typed task state and step-history records.
- **FR-002**: Keep goal, step index, context, history, and latest result in task state.
- **FR-003**: State advancement creates new values and does not mutate caller-owned nested inputs.
- **FR-004**: Provide finite step and model-call budgets with explicit remaining counts.
- **FR-005**: Budget consumption is immutable and rejects exhausted counters.
- **FR-006**: Validate external state and budget values at construction boundaries.
- **FR-007**: Do not implement routing, tool execution, verification, persistence, or an agent loop in this phase.
- **FR-008**: Offline tests cover transitions, immutability, invalid values, and exact exhaustion boundaries.

## Success Criteria

- State transitions and budget consumption are deterministic and immutable.
- Invalid goals, counters, and budget limits fail at construction or transition boundaries.
- Zero and exact-exhaustion cases are covered by offline tests.
- Ruff, strict mypy, and the full offline test suite pass.

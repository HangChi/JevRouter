# Feature Specification: Jev Verifier

**Feature Branch**: `006-verifier`
**Status**: Complete

## Goal

Evaluate whether the latest task result satisfies the user's goal using one typed Jev decision request. The verifier reports completion probability and result quality; it does not modify task state, route another action, or execute tools.

## User Stories

### US1 - Assess task completion

As an application developer, I need a calibrated probability that the latest result satisfies the original goal so a future runner can decide whether to stop or continue.

Acceptance scenarios:
1. A valid task snapshot and latest step result produce a typed completion probability.
2. The request includes the goal, action, result, and relevant context/history supplied in the state.
3. Missing result or a task with no completed step is rejected before any provider request.
4. Invalid or incomplete provider answers fail through the client's sanitized validation boundary.

### US2 - Assess result quality

As an application developer, I need a typed quality score and confidence alongside completion so the future runner can distinguish complete-but-poor results from useful results.

Acceptance scenarios:
1. The quality score is associated with the ordered quality legend submitted in the request.
2. Completion and quality are requested together in one provider call.
3. The returned assessment is immutable and preserves the selected model identifier.

## Requirements

- **FR-001**: Provide an asynchronous verifier over a `TaskState` and the injected `JevClient` and model identifier.
- **FR-002**: Submit one `noul` completion question and one `score` quality question in a single `systemone` request.
- **FR-003**: Include current goal, step/action, context, history, and latest result in the decision state.
- **FR-004**: Return an immutable typed assessment with completion probability, quality score/confidence, and model.
- **FR-005**: Reject state without a completed action/result before making provider I/O.
- **FR-006**: Leave completion thresholds and the action taken afterward to the future Runner.
- **FR-007**: Never mutate task state, execute tools, or loop.
- **FR-008**: Offline tests cover request shape, typed mapping, invalid state, client failures, and no state/tool side effects.

## Success Criteria

- A valid verification makes exactly one client request with both questions.
- Completion and quality values map from validated typed answers without reinterpretation.
- Invalid state is rejected without a request.
- Ruff, strict mypy, and the full offline test suite pass.

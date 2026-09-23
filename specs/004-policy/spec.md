# Feature Specification: Policy Engine

**Feature Branch**: `004-policy`
**Status**: Complete

## Goal

Convert a Router recommendation into a deterministic local control outcome, using explicit MVP thresholds and the trusted tool registry. The Policy Engine must not execute tools or interpret policy approval as user confirmation.

## User Stories

### US1 - Gate a recommended tool action

As an application developer, I need local thresholds to decide whether a registered recommendation may proceed, needs confirmation, or should be delegated.

Acceptance scenarios:
1. A registered tool recommendation below all thresholds yields `execute`.
2. A confirmation probability above 0.75 or risk score at least 2.5 yields `ask_confirmation`.
3. A reasoning probability above 0.70 or route confidence below 0.75 yields `delegate_to_llm` when confirmation is not required.
4. Equality follows the specified strict and non-strict comparisons.

### US2 - Keep control and authority local

As an application developer, I need explicit control-action mappings and fail-closed handling of unavailable tools so Jev output cannot trigger an unknown action.

Acceptance scenarios:
1. `ask_user`, `delegate_to_llm`, and `finish` map to corresponding outcomes.
2. An action absent from the current trusted registry yields `reject`.
3. Policy returns an outcome only; it never invokes a tool or completes a user-confirmation step.

## Requirements

- **FR-001**: Provide a synchronous policy evaluator over `RouteDecision` and `ToolRegistry`.
- **FR-002**: Return an immutable typed decision with finite outcome, action, and reason.
- **FR-003**: Use MVP thresholds: confirmation > 0.75, risk >= 2.5, reasoning > 0.70, and route confidence < 0.75.
- **FR-004**: Apply confirmation/risk checks before delegation checks.
- **FR-005**: Reject recommended tool actions that are not currently registered.
- **FR-006**: Map the three Router control actions to their control outcomes.
- **FR-007**: Never execute tools or imply explicit user approval.
- **FR-008**: Tests cover outcomes, boundaries, precedence, registry changes, and no execution.

## Success Criteria

- Policy results are deterministic for a route and the current registry.
- All threshold equality cases are covered by offline tests.
- Ruff, strict mypy, and the full offline test suite pass.

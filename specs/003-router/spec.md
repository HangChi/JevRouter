# Feature Specification: Decision Router

**Feature Branch**: `003-router`
**Status**: Complete

## Goal

Translate caller-supplied task state and trusted registered tools into one structured Jev routing recommendation. The Router does not authorize or execute the recommendation.

## User Stories

### US1 - Request a structured routing recommendation

As an application developer, I need one typed decision covering the next action, risk, confirmation, and reasoning so that later local policy can decide what is allowed.

Acceptance scenarios:
1. The Router sends exactly one Jev request with registered tools and the three control actions as choice candidates.
2. The request includes the five ordered risk levels and confirmation/reasoning Noul questions.
3. Validated Jev answers map into an internal typed decision; client failures propagate as typed errors.
4. An empty registry still allows `ask_user`, `delegate_to_llm`, and `finish`.

### US2 - Preserve application authority

As an application developer, I need a recommendation-only boundary so that model output cannot expand the allowlist or trigger side effects.

Acceptance scenarios:
1. Router never invokes a tool's `execute` method.
2. Router candidates come only from trusted registry configuration and fixed control actions.
3. Policy thresholds, authorization, and execution remain outside this phase.

## Requirements

- **FR-001**: Provide an async Router using the existing `JevClient.systemone` contract.
- **FR-002**: Build one request with `next_action`, `risk`, `requires_confirmation`, and `needs_reasoning` questions.
- **FR-003**: Include registry tool names/descriptions and `ask_user`, `delegate_to_llm`, `finish` as action candidates.
- **FR-004**: Use the documented five risk descriptions in their specified order.
- **FR-005**: Return a typed decision with selected action, action confidence, risk score/confidence, confirmation/reasoning probabilities, and model identifier.
- **FR-006**: Router MUST NOT authorize, execute tools, or apply policy thresholds.
- **FR-007**: Tests MUST be deterministic, offline, and cover request, mapping, empty-registry, and error behavior.
- **FR-008**: Policy engine, thresholds, runner, verifier, API, dashboard, and persistence are out of scope.

## Success Criteria

- Router request and response mapping tests pass using an injected mock transport.
- Registered tools are candidates but are never executed by Router.
- Ruff, strict mypy, and the complete offline test suite pass.

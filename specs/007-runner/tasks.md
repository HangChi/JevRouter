# Tasks: Bounded Runner

## Phase 1: Runner Contract

- [x] T001 Extract `jsonable()` into `jev_router/serialization.py` and reuse it in `verifier.py`.
- [x] T002 Define `RunStatus`, `StepTrace`, `RunResult` and the collaborator protocols in `jev_router/runner.py`.
- [x] T003 Validate model identifier, completion threshold and the `max_model_calls >= 2 * max_steps` budget invariant at construction.
- [x] T004 Assemble `Router`, `PolicyEngine` and `Verifier` from one shared `ToolRegistry`.

## Phase 2: Loop

- [x] T005 Check both budget counters before consuming either, then consume one step and one route model call per iteration.
- [x] T006 Map policy outcomes: `reject`, `ask_user`, `delegate_to_llm`, `execute`/`ask_confirmation`, and `finish`.
- [x] T007 Resolve arguments before confirmation and bind them to the `ConfirmationHandler` call.
- [x] T008 Require confirmation for `write` and `external` risk tools independently of the policy outcome.
- [x] T009 Fail closed when a required collaborator is absent.
- [x] T010 Verify after execution and on a `finish` recommendation with at least one step; skip verification when no step has run.
- [x] T011 Stop with `failed` on a second negative assessment of an unchanged state.
- [x] T012 Convert provider, tool, resolver and state errors into `failed` with a diagnostic.
- [x] T013 Emit one trace per iteration and for pre-decision terminations, without letting a sink failure abort the run.

## Phase 3: Tests and Documentation

- [x] T014 Export the public runner types from the package.
- [x] T015 Test completion, continuation, finish, budget exhaustion, confirmation gating, delegation, user input, failure modes, traces and immutability in `tests/test_runner.py`.
- [x] T016 Document scope, data model and phase boundaries in this spec directory.
- [x] T017 Update architecture and development documentation for the Runner's budget ownership and fail-closed defaults.
- [x] T018 Run Ruff, strict mypy and full offline pytest; review the authority boundary.

## Dependencies

T001 precedes T002 and T012. T002–T004 precede T005–T013. T014–T018 follow implementation and tests.

## Completion Criteria

All tasks are checked only after implementation and validation. The Runner owns budget consumption and termination; it does not mutate state in place, execute unregistered actions, block on a human, or implement the LLM adapter.

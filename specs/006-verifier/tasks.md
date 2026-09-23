# Tasks: Jev Verifier

## Phase 1: Verifier Contract

- [x] T001 Define the completion/quality question contract and immutable `VerificationDecision` in `jev_router/verifier.py`.
- [x] T002 Build the JSON-compatible decision state from `TaskState` snapshots.
- [x] T003 Reject state without a completed step or latest result before any provider I/O.
- [x] T004 Implement one-request async verification and typed answer mapping.
- [x] T005 Export the public verifier types from the package.

## Phase 2: Tests and Documentation

- [x] T006 Test request shape, decision state, typed mapping, invalid state, client failures, and no state mutation in `tests/test_verifier.py`.
- [x] T007 Document scope, data model, and phase boundaries in this spec directory.
- [x] T008 Update architecture and development documentation for the verifier's assessment-only role.
- [x] T009 Run Ruff, strict mypy, and full offline pytest; review the authority boundary.

## Dependencies

T001 precedes T004–T006. T002–T003 precede T004. T006–T009 follow implementation and tests.

## Completion Criteria

All tasks are checked only after implementation and validation. The Verifier reports an assessment only; it does not mutate state, execute tools, or decide stop/continue policy.

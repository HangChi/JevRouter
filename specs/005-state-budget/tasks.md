# Tasks: Task State and Budget

## Phase 1: State Contract

- [x] T001 Define immutable step records and task state with JSON snapshot isolation in `jev_router/state.py`.
- [x] T002 Implement validated state advancement and history updates.
- [x] T003 Define immutable finite step/model-call budgets and consumption methods.
- [x] T004 Export the public state and budget types from the package.

## Phase 2: Tests and Documentation

- [x] T005 Test state initialization, transitions, input isolation, invalid values, and history consistency.
- [x] T006 Test budget creation, zero limits, exact exhaustion, and immutable consumption.
- [x] T007 Document scope, data model, and phase boundaries in this spec directory.
- [x] T008 Update architecture and development documentation for state and budget ownership.
- [x] T009 Run Ruff, strict mypy, and full offline pytest.

## Dependencies

T001 precedes T002 and T005. T003 precedes T006. T004–T009 follow their relevant implementation.

## Completion Criteria

All tasks are checked only after implementation and validation. State and budget operations are immutable, bounded, deterministic, and do not orchestrate external work.

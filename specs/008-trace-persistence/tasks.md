# Tasks: Trace Persistence

## Phase 1: Storage Contract

- [x] T001 Create the `apps/api` package and define `SCHEMA_VERSION`/`PAYLOAD_VERSION`.
- [x] T002 Define the `tasks`, `agent_steps` and `evaluations` schema with cascading keys and indexes.
- [x] T003 Implement versioned payload encode/decode with `_degrade` fallback.
- [x] T004 Record the schema version and refuse a database newer than this build.

## Phase 2: Reads and Writes

- [x] T005 Implement `record(RunResult)` as one idempotent transaction.
- [x] T006 Implement `sink()` writing each step under a `running` task marker.
- [x] T007 Implement `load_traces` reconstructing `StepTrace` values via a steps/evaluations join.
- [x] T008 Implement `load_task` and `list_tasks` returning `TaskRecord`.
- [x] T009 Apply the optional redaction callback before encoding.
- [x] T010 Provide connection lifecycle: `close()` and the context manager.

## Phase 3: Tests and Documentation

- [x] T011 Test round-trip equality, task fields and evaluation separation in `tests/test_storage.py`.
- [x] T012 Test incremental sink writes, finalization and idempotency.
- [x] T013 Test payload and schema version refusal, and malformed payloads.
- [x] T014 Test redaction coverage, degradation of unserializable values, and task isolation.
- [x] T015 Test that a run driven with a sentinel credential stores none of it.
- [x] T016 Document scope, data model and phase boundaries in this spec directory.
- [x] T017 Update architecture and development documentation for the storage layer.
- [x] T018 Extend static checks to `apps`, and run Ruff, strict mypy and full offline pytest.

## Dependencies

T001–T004 precede T005–T010. T011–T018 follow implementation and tests.

## Completion Criteria

All tasks are checked only after implementation and validation. Storage only consumes the immutable records the Runner already produces; it adds no behaviour to the core loop and holds no database code inside `jev_router`.

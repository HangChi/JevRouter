# Feature Specification: Trace Persistence

**Feature Branch**: `008-trace-persistence`
**Status**: Complete

## Goal

Persist the traces the Runner already produces so a run can be inspected after the process exits. Storage consumes the immutable records from phase 7 and adds no new behaviour to the core loop.

## User Stories

### US1 - Inspect a finished run

As an application developer, I need to read back a run's task, steps and evaluations so a dashboard can show what happened.

Acceptance scenarios:
1. Recording a `RunResult` writes its task, steps and evaluations.
2. Reading the task back returns its goal, terminal status, step count, diagnostic and final state.
3. Reading the steps back returns records equivalent to the `StepTrace` values the Runner emitted.
4. An unknown task reads as absent rather than raising.

### US2 - Inspect a run that is still going

As an application developer, I need each step written as it happens so a killed process still leaves a diagnosable trace.

Acceptance scenarios:
1. The store exposes a `TraceSink` that writes each step on emission.
2. A task written only by the sink is marked `running` until `record()` finalizes it.
3. `record()` replaces the running status with the terminal one without duplicating steps.

### US3 - Read old traces after the format changes

As an application developer, I need stored payloads to carry their format version so a schema change is detectable instead of silently misread.

Acceptance scenarios:
1. Every stored JSON payload is wrapped in a versioned envelope.
2. A payload with an unknown version is refused with a clear error.
3. A malformed payload is refused with a clear error.
4. A database whose schema version is newer than this build is refused.

### US4 - Keep credentials and unreadable values out of the way

As an application developer, I need storage that cannot leak a credential and cannot lose a run because one value would not serialize.

Acceptance scenarios:
1. A run driven with a real client configuration stores no credential anywhere in the database file.
2. A redaction callback is applied to results, arguments and state snapshots before encoding.
3. A value the state snapshot already refused degrades to a marker that leaves the rest of the run readable.

## Requirements

- **FR-001**: Provide a SQLite-backed store for `tasks`, `agent_steps` and `evaluations`, driven only by `RunResult` and `StepTrace`.
- **FR-002**: Place the store in the API layer; the core package gains no database dependency.
- **FR-003**: Wrap every stored JSON payload in a versioned envelope and refuse unknown or malformed versions on read.
- **FR-004**: Record the schema version and refuse a database newer than this build.
- **FR-005**: Provide both an incremental sink and a whole-run `record()`, both idempotent for a repeated task.
- **FR-006**: Reconstruct `StepTrace` values and a `TaskRecord` on read.
- **FR-007**: Apply an optional redaction callback before encoding results, arguments and state snapshots.
- **FR-008**: Degrade values JSON cannot hold instead of failing the whole write.
- **FR-009**: Store no credential; the store never receives client configuration.
- **FR-010**: Offline tests cover round-trip, incremental writes, versioning, redaction, degradation, isolation and the credential guarantee.

## Success Criteria

- A recorded run reads back with every trace field preserved.
- A sink-written run is queryable before it finishes.
- No credential appears anywhere in the database file.
- Ruff, strict mypy and the full offline test suite pass.

## Non-Goals

- HTTP endpoints, task submission, or confirmation workflows (the API phase).
- Trace retention, deletion or access-control policy.
- Migrations between schema versions; an unknown version is refused, not converted.
- Async database drivers or a background writer.
- Changes to the core package's trace or state contracts.

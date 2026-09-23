# Implementation Plan: Trace Persistence

## Summary

Add `apps/api/storage.py`: a SQLite `TraceStore` that persists the `RunResult` and `StepTrace` values the Runner already produces, plus an incremental sink for runs still in progress.

## Technical Context

- Core package: `jev_router` (unchanged by this phase).
- New location: `apps/api/`, because `docs/development.md` states the core package avoids database implementations and `docs/architecture.md` lists storage under `apps/api/`.
- Input contracts: `RunResult` (status, task_id, state, budget, traces, diagnostic) and `StepTrace`.
- JSON conversion: `jev_router.serialization.jsonable`, already shared by the verifier and runner.
- Storage: stdlib `sqlite3`; no new dependency and no change to the synchronous `TraceSink` contract from phase 7.
- Tests: offline pytest against a temporary database file.

## Design

Three tables mirror the three trace concepts. `tasks` holds one row per run with its terminal status, step count, diagnostic and final state. `agent_steps` holds one row per `StepTrace`. `evaluations` holds the `VerificationDecision` separately, keyed by `(task_id, step)`, so the assessment is not duplicated inside the step row.

`PRAGMA user_version` records the schema version; opening a database with a newer version is refused rather than migrated. Every JSON column stores `{"version": N, "data": ...}`, so a future payload change is detectable per value instead of silently misread.

Two write paths share one `_write_step` upsert:

- `record(result)` writes the terminal task row and every trace in one transaction.
- `sink()` returns a `TraceSink` that upserts a `running` task row on first emission and writes each step as it arrives, so a killed process still leaves a readable trace.

Both are idempotent for a repeated `(task_id, step)`, so `record()` after `sink()` finalizes without duplicating.

Reads reconstruct the original values: `load_traces` joins steps to evaluations and returns `StepTrace` objects, and `load_task` returns a `TaskRecord`. A round-trip test asserts equality with the Runner's own values.

Encoding degrades rather than fails. A tool runs before its output is accepted, so a trace can hold a value `TaskState.advance` already refused; `_degrade` replaces only the offending leaves with `{"__unserializable__": ...}` and keeps the rest of the run readable. Non-finite floats get the same treatment because `json.dumps(allow_nan=False)` would otherwise reject the whole write.

An optional `redact` callback runs before encoding on results, arguments and state snapshots. This is the hook `docs/security.md` asks for before persisting user goals and tool I/O; retention and deletion policy remain out of scope.

The credential guarantee is structural: the store only ever sees `RunResult`/`StepTrace`, never `JevClientConfig`. A test drives a real `Runner` with a sentinel key and asserts the bytes do not appear in the database file.

The connection is created in `__init__` and closed by `close()` or the context manager. Writes are synchronous and short, matching the synchronous `TraceSink`; the store is documented as single-threaded and driven from one event loop.

## Non-Goals

- HTTP layer, task submission or confirmation flow.
- Retention, deletion or access control.
- Schema migrations.
- Async drivers, background writers, or connection pooling.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router apps`, and `uv run pytest`. Cover round-trip equality, incremental writes before completion, payload and schema versioning, redaction, degradation, task isolation, idempotency and the credential guarantee.

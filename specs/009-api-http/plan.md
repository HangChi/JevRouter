# Implementation Plan: API HTTP Boundary

## Summary

Add `apps/api/{config,schemas,service,app}.py`: a FastAPI application that starts runs in the background, resolves their confirmation and input prompts over later requests, and serves traces from the SQLite store.

## Technical Context

- Core package: `jev_router` (unchanged).
- Existing API-layer modules: `apps/api/storage.py` from phase 8.
- Runner contracts: `Runner(..., confirmation=..., user_input=..., trace_sink=...)` and `RunResult`.
- HTTP: FastAPI with uvicorn; both added as runtime dependencies this phase.
- Tests: `fastapi.testclient.TestClient` against a temporary database; no network.

## Design

Four modules, one responsibility each:

- `config.py` — a frozen `Settings` pydantic model plus `from_env()`. Everything is validated once at startup, including `max_model_calls >= 2 * max_steps`, so a misconfigured deployment refuses to serve rather than failing on the first task. The Jev portion reuses the already-tested `JevClientConfig.from_env()`.
- `schemas.py` — strict request/response models (`extra="forbid"`) and the live-status constants.
- `service.py` — `TaskService`, the run registry.
- `app.py` — the app factory, routes and error mapping.

### Background runs and futures

`TaskService.submit()` builds a Runner whose `ConfirmationHandler` and `UserInputHandler` are per-run adapters bound to the task id, then schedules `_drive()` with `create_task`. The request returns immediately.

Because `UserInputHandler.request_input` receives no task id, both handlers go through one `_RunHandlers` adapter that already knows it.

Each handler registers an `asyncio.Future` on the service and flips the handle to `awaiting_confirmation` / `awaiting_input`, then awaits. `POST /tasks/{id}/confirm` and `POST /tasks/{id}/input` resolve the corresponding future. The Runner is unchanged: it simply awaits a handler that happens to be waiting for a human.

This matters because a stop-and-restart design would re-execute side effects from earlier steps. Keeping the run alive avoids that entirely.

### Route handlers are async

The handlers are declared `async def` so `asyncio.get_running_loop()` inside `submit()` succeeds. FastAPI runs sync handlers in a threadpool, where there is no running loop.

### Live vs terminal status

`RunStatus` describes a finished run. A run in flight needs three more states, defined in `schemas.py`: `running`, `awaiting_confirmation`, `awaiting_input`. The handle carries the live status; `record()` replaces the stored `running` marker with the terminal status.

### Trace emission while blocked

A step blocked on a human has not completed, so the Runner has not emitted its trace yet. What is pending is reported by the task view (`pending_confirmation` / `pending_input`), not by the trace list. This keeps one trace per completed step rather than emitting partial records.

### Error mapping

- Unknown task id → `404` on every task-scoped route.
- A prompt endpoint called when nothing is pending → `409`.
- A body that fails the strict schema → `422` from FastAPI's validation.
- `GET /tasks?limit=0` → `400`.

### Persistence failure is not a run failure

`record()` is called after the handle has been updated with the run's real terminal status. If it raises, the status stands and the diagnostic records that persistence failed — the sink already wrote the individual steps. Reaching an exception here at all would mean the store itself is broken.

## Non-Goals

- Auth, rate limiting, multi-tenancy, cancellation or restart resumption.
- Streaming responses or the Web dashboard.
- Changes to the core package.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router apps`, and `uv run pytest`. Cover every endpoint, every error mapping, the confirmation and input round trips, list ordering, startup validation, and the credential guarantee. Separately boot the app under uvicorn against a temporary database and exercise the endpoints with curl.

# Data Model: API HTTP Boundary

## Statuses

Two vocabularies, deliberately separate:

- **Terminal** — `RunStatus` from the core package: `completed`, `needs_user_input`, `needs_confirmation`, `rejected`, `budget_exhausted`, `failed`.
- **Live** — defined in `apps/api/schemas.py` for a run that has not finished: `running`, `awaiting_confirmation`, `awaiting_input`.

`TraceStore` also uses `running` as its stored marker for a task whose traces are still being written; `record()` replaces it with the terminal status. The two uses coincide.

## RunHandle

In-memory record of one run, owned by `TaskService`:

- `task_id`, `goal`, `status`, `step`, `diagnostic`.
- `pending_confirmation`: `PendingConfirmation(action, arguments, step)` or `None`.
- `pending_input`: `PendingInput(question, step)` or `None`.

The handle is not persisted. A process restart loses in-flight runs; their traces remain in SQLite.

## Futures

`TaskService` holds `dict[str, asyncio.Future]` for confirmations and inputs, keyed by task id. A run is sequential, so at most one of each is pending per task. The futures are dropped in `_drive`'s `finally` and on `shutdown()`.

## Settings

Frozen pydantic model built by `from_env()`:

| Field | Environment variable | Default |
| --- | --- | --- |
| `model` | `JEV_MODEL` (required) | — |
| `database_path` | `JEV_DATABASE_PATH` | `traces.db` |
| `workspace_root` | `JEV_WORKSPACE_ROOT` | `./workspace` |
| `max_steps` | `JEV_MAX_STEPS` | `8` |
| `max_model_calls` | `JEV_MAX_MODEL_CALLS` | `16` |
| `completion_threshold` | `JEV_COMPLETION_THRESHOLD` | `0.75` |
| `jev` | `JEV_API_KEY`, `JEV_BASE_URL`, `JEV_TIMEOUT_SECONDS` | vendor defaults |

Validation: blank strings rejected, `max_steps >= 1`, `completion_threshold` in `[0, 1]`, and `max_model_calls >= 2 * max_steps`. A non-numeric numeric field raises with the variable name.

## Endpoints

| Method | Path | Success | Errors |
| --- | --- | --- | --- |
| POST | `/tasks` | `202` `SubmitTaskResponse` | `422` |
| GET | `/tasks` | `200` `TaskListResponse` | `400` for `limit < 1` |
| GET | `/tasks/{id}` | `200` `TaskView` | `404` |
| GET | `/tasks/{id}/traces` | `200` `TraceListResponse` | `404` |
| POST | `/tasks/{id}/confirm` | `204` | `404`, `409`, `422` |
| POST | `/tasks/{id}/input` | `204` | `404`, `409`, `422` |

`GET /tasks` returns newest first, matching `TraceStore.list_tasks`.

## TraceView

Flattens `StepTrace` for transport: the routing probabilities, policy result, execution result, arguments, the completion probability and quality score lifted out of `VerificationDecision`, and the state snapshot. `state_snapshot` is included because it is what the provider actually saw.

## Default registry

`default_registry(settings)` registers `calculator`, `write_file` (under `workspace_root`) and `send_mock_email`. The two search tools are omitted because they need documents injected by the caller.

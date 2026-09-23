# Data Model: Trace Persistence

## Tables

### tasks

One row per run.

- `task_id`: primary key, matching `RunResult.task_id`.
- `goal`: the original goal.
- `status`: terminal `RunStatus`, or `running` while the sink is still writing.
- `step`: completed step count from the final `TaskState`.
- `diagnostic`: `RunResult.diagnostic`, nullable.
- `created_at`, `updated_at`: timezone-aware UTC ISO-8601 timestamps.
- `final_state`: versioned JSON of goal, step, context, history and last result.

### agent_steps

One row per `StepTrace`, primary key `(task_id, step)`, cascading from `tasks`.

- `action`, `policy_outcome`, `policy_reason`.
- `route_confidence`, `route_risk`, `requires_confirmation`, `needs_reasoning`: nullable, because steps that stop before a decision have no route.
- `confirmed`: nullable integer (`NULL` when no confirmation was required).
- `executed`: integer boolean.
- `result`, `arguments`, `state_snapshot`: versioned JSON, redacted before encoding.
- `model`, `duration_ms`.

### evaluations

One row per verification, primary key `(task_id, step)`, cascading from `tasks`.

- `completion_probability`, `quality_score`, `quality_confidence`.
- `quality_legend`: JSON array of the ordered labels.
- `model`.

The assessment lives here rather than in `agent_steps` so a step row is not duplicated; `load_traces` joins the two.

## Versioning

Two independent versions:

- **Schema version** — `PRAGMA user_version`, currently `1`. A database with a newer value is refused on open.
- **Payload version** — embedded in every JSON column as `{"version": 1, "data": ...}`. A value with an unknown version, or one that is not a versioned envelope at all, is refused on read.

Neither is migrated automatically. Refusing is the safe default: a silent misread would corrupt the trace record.

## Degradation

`_encode` falls back to `_degrade` when a value cannot be serialized. `_degrade` walks the structure and replaces only the offending leaves:

- an unserializable object becomes `{"__unserializable__": "<type name>"}`;
- a non-finite float becomes `{"__unserializable__": "non-finite float"}`.

Everything else in the value is preserved, so a single bad tool output does not cost the whole run.

## TaskRecord

Read model returned by `load_task` and `list_tasks`: `task_id`, `goal`, `status`, `step`, `diagnostic`, `created_at`, `updated_at`, `final_state`.

## Running status

`RUNNING_STATUS = "running"` is a persistence-level marker for a task whose traces are still being written. It is not part of `RunStatus`; `record()` replaces it with the terminal status.

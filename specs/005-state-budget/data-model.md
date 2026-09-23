# Data Model: Task State and Budget

## StepRecord

An immutable history item containing the one-based step number, selected action, and optional result snapshot.

## TaskState

An immutable task snapshot containing:

- `goal`: non-empty normalized goal text.
- `step`: non-negative completed-step count.
- `context`: JSON-compatible state supplied by the application.
- `history`: ordered immutable step records.
- `last_result`: optional JSON-compatible result from the latest step.

`advance(action, result)` returns a new state with `step + 1`, a new history record, and the new last result. It does not mutate the source state or nested caller-owned values.

## ExecutionBudget

An immutable pair of step and model-call limits and remaining counts. Each consume operation returns a new budget with one remaining count decremented. A zero remaining count rejects consumption. Limits and remaining values are finite non-negative integers with remaining values no greater than their corresponding limits.

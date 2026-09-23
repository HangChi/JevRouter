# Data Model: Bounded Runner

## RunStatus

Terminal status of one run:

- `completed`: the verifier's completion probability reached the threshold, or a `finish` recommendation arrived before any step ran.
- `needs_user_input`: the policy requested more information and none was provided.
- `needs_confirmation`: confirmation was required and was absent, denied, or had no handler.
- `rejected`: the recommended action is not (or no longer) registered.
- `budget_exhausted`: step or model-call allowance ran out before the loop could finish.
- `failed`: a provider error, tool input rejection, state rejection or missing collaborator stopped the run.

## RunResult

Immutable outcome of `Runner.run()`:

- `status`: terminal `RunStatus`.
- `task_id`: caller-supplied identifier, or a generated one.
- `state`: the final `TaskState` snapshot.
- `budget`: the remaining `ExecutionBudget`.
- `traces`: ordered `StepTrace` records, never empty for a started run.
- `diagnostic`: human-readable reason, present for every non-completed status.

## StepTrace

Immutable record of one iteration:

- `step`, `task_id`, `action`: position and the recommended action.
- `executed`: whether a registered tool was invoked. `ask_user` and `delegate_to_llm` leave it `false` because they produce no side effect.
- `result`: whatever the step produced (tool output, user input, or delegated text).
- `policy_outcome`, `policy_reason`: the local authorization result.
- `route_confidence`, `route_risk`, `requires_confirmation`, `needs_reasoning`: provider probabilities.
- `confirmed`: the approval decision, or `null` when none was required.
- `arguments`: the resolved argument mapping bound to the confirmation.
- `verification`: the `VerificationDecision`, when a verification ran.
- `state_snapshot`: the JSON payload sent to the provider for this step.
- `model`: provider model identifier.
- `duration_ms`: wall-clock iteration duration.

Routing fields are nullable because paths that stop before a decision (budget exhaustion, provider failure) have none.

## Collaborators

Protocols injected by the caller. `ActionInputResolver` is the seam for argument synthesis, which is an LLM responsibility outside this phase; its default `{}` is rejected by each tool's own input schema, so a missing resolver fails closed rather than executing with invented arguments.

## Budget

`ExecutionBudget` is unchanged. The Runner consumes one step per iteration and one model call per route, verification and delegation. Construction requires `max_model_calls >= 2 * max_steps`. Because each step costs at least two model calls, the model-call guards in `_verify` and the delegation branch are defensive: given the invariant, steps are exhausted first or simultaneously.

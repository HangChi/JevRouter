# Implementation Plan: Bounded Runner

## Summary

Add `jev_router/runner.py`: one bounded loop that consumes the existing Router, Policy Engine, TaskState/budget and Verifier, plus injectable collaborators for the actions the core cannot perform itself.

## Technical Context

- Core package: `jev_router`.
- Existing public decisions: `RouteDecision`, `PolicyDecision`/`PolicyOutcome`, `VerificationDecision`.
- Existing state contract: `TaskState.advance()`, `ExecutionBudget.consume_step()/consume_model_call()`.
- Provider boundary: `JevClient.systemone` validates the payload with `json.dumps(allow_nan=False)`, so routing payloads must be plain JSON.
- Deferred obligation: `specs/004-policy/plan.md` left the coarse `Tool.risk` category unenforced; `docs/security.md` requires the Runner to apply it.
- Tests: offline pytest with `httpx.MockTransport`; no live requests.

## Design

`Runner.__init__` takes `client`, `model`, `tools`, `budget`, `completion_threshold` and four optional collaborators, then constructs `Router`, `PolicyEngine` and `Verifier` itself. Assembling them internally makes "one shared `ToolRegistry`" structural rather than conventional, so the execution-time registration recheck cannot be bypassed by a divergent instance.

Collaborators are `Protocol`s so tests can stub them:

| Protocol | Method | Absent behaviour |
| --- | --- | --- |
| `ActionInputResolver` | `resolve(action, state) -> Mapping` | yields `{}`; the tool's own schema rejects it |
| `ConfirmationHandler` | `confirm(task_id, action, arguments, state) -> bool` | `needs_confirmation` |
| `UserInputHandler` | `request_input(question, state) -> str \| None` | `needs_user_input` |
| `DelegateHandler` | `delegate(state) -> str` | `failed` |
| `TraceSink` | `emit(trace)` | no live delivery; traces stay in `RunResult.traces` |

`ActionInputResolver` exists because `RouteDecision` carries an action name but no arguments, and argument synthesis is an LLM responsibility this phase deliberately does not implement. It is optional rather than required so the Runner does not force an LLM dependency; the default `{}` fails closed through each tool's own input schema.

The loop checks both budget counters before consuming either, so a stop never happens after a partial consumption. `execute`/`ask_confirmation` resolve arguments first, then confirm, then execute — the reverse order would let a user approve an action while different arguments run, which `docs/security.md` forbids. `_needs_confirmation` ORs the policy's `ask_confirmation` outcome with `tool.risk in {"write", "external"}`.

A private `_Stop` exception carries terminal statuses out of deeply nested iteration code, keeping one `_settle` site that seals the final trace and builds the `RunResult`. `_verify` returns a `_Verified` value rather than raising, because "verification said incomplete" is a normal outcome, not an error.

`_verify` also detects no progress: `advance()` returns a new `TaskState`, so `verified is state` reliably detects a second negative assessment of the same unchanged snapshot and stops with `failed` instead of re-routing an identical payload.

Construction validates `max_model_calls >= 2 * max_steps`, because one executing iteration needs one route plus one verify. Without it a run could report `budget_exhausted` for a task that was actually completable.

## Controlled refactor

`jev_router/serialization.py` gains `jsonable(value)`, extracted verbatim from `verifier._jsonable`. `verifier.py` imports it; the Runner reuses it for the routing payload. Behaviour is unchanged and `tests/test_verifier.py` locks the verifier's payload shape.

## Non-Goals

- Runner persistence, task identity on `TaskState`, or serialization of traces.
- LLM adapter, model discovery, retries, or Jev client changes.
- Threshold calibration or per-tool policy overrides.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Cover completion and continuation, the finish path, budget exhaustion, confirmation gating by tool risk, argument binding, delegation, user input, every failure mode, trace emission and immutability.

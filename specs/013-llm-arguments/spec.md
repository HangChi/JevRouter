# Feature Specification: LLM Argument Synthesis

**Feature Branch**: `013-llm-arguments`
**Status**: Complete

## Goal

Close the last functional gap: make the agent able to execute a tool in a real
deployment. `jev_router` exposes an `ActionInputResolver` seam because a
`RouteDecision` carries an action name and no arguments, and argument synthesis
is an LLM responsibility — but nothing has ever filled that seam, so
`create_app()` defaults to `{}` and every tool call fails with
`tool 'X' rejected its input`. This phase fills it with an LLM-backed resolver
built on the client phase 11 added, gated by the same settings as delegation.

## Background

`docs/development.md` records the deferral explicitly: "`ActionInputResolver` 是
参数合成的接缝……本阶段不实现 `clients/llm.py`". Phase 11 built that client for
the eval baseline and the delegate handler; the resolver is its third consumer
and the one the run path cannot work without.

The resolver needs to tell the model what arguments a tool accepts. The `Tool`
protocol exposes `name`, `description` and `risk` but nothing about its input, so
a model can only guess field names and every call would fail validation. The
protocol therefore gains the input model the tool already validates against —
single source of truth, impossible to drift from the check that actually runs.

## Scope

In scope:

- `Tool` gains `input_model: type[BaseModel]`; the five MVP tools declare theirs.
- Field descriptions on the four input models, so the generated schema carries
  the constraints prose a model needs (a relative `write_file` path, the
  expression grammar, the search semantics) instead of bare types.
- `apps/api/llm.py`: the LLM-backed Runner collaborators — the argument resolver
  and the delegate handler phase 11 put in `service.py`.
- Wiring: both are assembled from the same `llm`/`llm_model` settings pair, and
  both stay absent when the LLM is unconfigured.
- Tests for the prompt, the parse, the failure paths and an end-to-end run that
  executes a real tool through the HTTP boundary.

Out of scope:

- A second settings switch for the resolver: one LLM configuration drives both
  collaborators, because an agent that can reason but not parameterize is not
  useful.
- Any change to `Runner`, the tools' validation, or the Policy Engine.

## User Stories

### US1 - Execute a tool with synthesized arguments

As an operator, I need a routed action to be executed with arguments the LLM
synthesized from the goal and history, so a run does something instead of
stopping at "the tool rejected its input".

Acceptance scenarios:

1. With an LLM configured, a route to `calculator` produces
   `{"expression": ...}` from the model and the tool executes.
2. The prompt carries the goal, the step, the history, the action, the tool's
   description and its input schema with field descriptions.
3. The arguments that reach the tool are the model's, and the trace records them
   in `arguments` as it already does for an injected resolver.

### US2 - Fail visibly when synthesis fails

As an operator, I need a failed synthesis to stop the run with a diagnostic
rather than execute a tool with guessed arguments.

Acceptance scenarios:

1. A provider error becomes a failed run whose diagnostic names the error
   category.
2. A completion that is not a JSON object, or names no field the tool accepts,
   becomes a failed run rather than a tool call with empty arguments.
3. With no LLM configured the behaviour is unchanged: the resolver is absent and
   the run fails the way phase 7 shipped it.

### US3 - Keep the tool as the authority on its input

As a reviewer, I need the model's output to remain untrusted input, so a
synthesized argument cannot widen what a tool accepts.

Acceptance scenarios:

1. The resolver returns the model's object unchanged; the tool's own pydantic
   model still validates it, and a violating argument fails exactly as a
   hand-written one would.
2. The schema in the prompt is derived from that same model, so the prompt
   cannot advertise a field the tool would refuse.

## Non-Goals

- No multi-turn argument refinement, no retry on validation failure (the run
  stops and the trace says why).
- No schema for control actions: `ask_user`, `delegate_to_llm` and `finish` never
  reach the resolver, because the Policy Engine branches them before execution.
- No change to how `write_file`'s path sandbox or `calculator`'s AST whitelist
  validate.

## Dependencies

- Phase 11: `jev_router/clients/llm.py`, the settings pair and the delegate
  wiring this phase reuses.
- Phase 2: the `Tool` protocol and the five tools whose input models become
  visible.

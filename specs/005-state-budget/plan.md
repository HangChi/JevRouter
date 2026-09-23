# Implementation Plan: Task State and Budget

## Summary

Add an immutable domain model for task progress and a deterministic budget value object. These are the foundations for the later execution loop without coupling this phase to providers, tools, or persistence.

## Technical Context

- Core package: `jev_router`.
- Existing public decisions: `RouteDecision` and `PolicyDecision`.
- State payloads may be JSON-compatible scalar/container values supplied by the application.
- Tests: offline pytest only; no Jev request or tool execution is needed.

## Design

Use frozen dataclasses for `TaskState`, `StepRecord`, and `ExecutionBudget`. Deep-copy caller-owned JSON-compatible values on construction and transitions to ensure state snapshots cannot be altered through retained input references. Task state includes goal, current step index, context, immutable history, and optional latest result. Advancing appends one record and returns a new state. Budget records maximum and remaining step/model-call counts; consume methods return new budgets and raise `ValueError` when the requested counter is exhausted. Limits are finite non-negative integers; bool is not accepted as an integer limit.

No status machine or orchestration behavior is added: finish/stop outcomes remain the responsibility of the future runner contract. No storage serialization is added in this phase.

## Non-Goals

- Router, policy, model calls, or tool execution.
- Verifier, runner loop, persistence, API, dashboard, or eval runner.
- Timeouts, monetary budgets, token estimates, or dynamic budget refill.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Test snapshot isolation, single-step advancement, initial and exact exhaustion, zero limits, and invalid construction/consumption values.

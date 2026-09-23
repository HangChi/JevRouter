# Implementation Plan: Policy Engine

## Summary

Add a deterministic local policy gate that consumes `RouteDecision` and returns a typed outcome without executing tools.

## Technical Context

- Core package: `jev_router`.
- Router contract: `jev_router.router.RouteDecision`.
- Trusted tool allowlist: `ToolRegistry.names()`.
- MVP thresholds and precedence: `doc.md` section 5.
- Tests: offline pytest; no Jev request is needed.

## Design

`PolicyEngine` receives a `ToolRegistry` and evaluates one `RouteDecision`. Control actions map to `ASK_USER`, `DELEGATE_TO_LLM`, and `FINISH`. Unknown or no-longer-registered tool actions yield `REJECT`. Registered tool actions first check confirmation probability > 0.75 or risk >= 2.5, then reasoning probability > 0.70 or action confidence < 0.75, and otherwise yield `EXECUTE`. `PolicyDecision` is immutable and contains its outcome, original action, and concise reason. An `EXECUTE` outcome authorizes only the next caller-controlled step; the Policy Engine neither invokes tools nor supplies explicit user confirmation.

Thresholds are MVP defaults, not vendor guidance. The coarse `Tool.risk` category does not add unrequested policy behavior in this phase.

## Non-Goals

- Tool execution or caller confirmation workflow.
- Threshold calibration, configuration services, or per-tool overrides.
- Runner, verifier, persistence, API, dashboard, or live integrations.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Cover all outcomes, threshold equality, precedence, unknown and removed tools, and non-execution.

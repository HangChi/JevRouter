# Implementation Plan: Decision Router

## Summary

Add a recommendation-only Router that packages trusted candidate actions and task state into one Jev request, then maps typed answers to an internal decision. It does not implement policy or execute tools.

## Technical Context

- Python package: `jev_router`.
- Jev questions and answers: reuse `jev_router.clients.jev` typed models and validation.
- Candidates: ordered `ToolRegistry.names()` and each trusted tool's description, followed by fixed control actions.
- Testing: pytest and `httpx.MockTransport`; no live requests.
- Static checks: Ruff and strict mypy.

## Design

`Router.route(state)` submits one request containing a choice over registered tools plus `ask_user`, `delegate_to_llm`, and `finish`, one five-level risk score, and two Noul questions. It maps answer values and confidence fields into immutable `RouteDecision`. The registry is only queried for names/metadata; its execution method is never called. No policy threshold or authorization decision is made.

## Non-Goals

- Policy engine or threshold decisions.
- Tool execution, agent loop, verifier, API, dashboard, or persistence.
- Model discovery, retries, or changes to the Jev client contract.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Verify one request, all four question types, fixed action candidates, ordered risk legend, answer mapping, typed client errors, empty registry behavior, and no tool execution.

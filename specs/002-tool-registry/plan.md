# Implementation Plan: Tool Registry and MVP Tools

## Summary

Deliver a small synchronous tool layer with typed result/risk contracts, a trusted in-memory registry, and five bounded offline MVP tools. The phase does not implement routing or authorization policy.

## Technical Context

- Python package: `jev_router.tools`.
- Validation: Pydantic v2 at tool input boundaries.
- Registry: in-memory, application-configured, duplicate names rejected.
- Testing: pytest with deterministic fixtures and temporary directories; no network access.
- Static checks: Ruff and strict mypy.

## Design

`Tool` is a protocol with `name`, `description`, a `RiskLevel`, and synchronous `execute(input) -> ToolResult`. `ToolRegistry` owns only trusted registrations, lookup, and dispatch. Each tool validates its input and owns its local behavior. Search and web-search fixtures are injected. Calculator accepts only a bounded arithmetic AST. File writing resolves a relative target beneath a configured root and rejects symlink escape, excessive UTF-8 content, and overwrites by default. Mock email validates metadata and returns a simulation.

## Non-Goals

- Model-driven registration or authority decisions.
- Router, policy engine, runner, verifier, agent loop, API, dashboard, persistence, or live service integrations.
- Arbitrary URL fetching, shell execution, real email, or calculator `eval`.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Tests cover registered tool dispatch, duplicate/unknown names, calculator syntax and limits, injected search data, file boundaries and overwrite controls, and mock email validation/simulation. All tests must remain offline.

## Operational Constraint

File containment assumes no hostile concurrent process can replace path components with symlinks between validation and file open; deployments must protect the configured root accordingly.

# Implementation Plan: Jev Verifier

## Summary

Add a small asynchronous adapter that asks Jev, in one request, whether the latest task result satisfies its goal and how useful that result is. It returns an assessment only; orchestration and stop/continue policy remain outside this phase.

## Technical Context

- Client: `jev_router.clients.jev.JevClient.systemone`.
- Input: immutable `jev_router.state.TaskState`.
- Typed questions/answers: existing `NoulQuestion`/`NoulAnswer` and `ScoreQuestion`/`ScoreAnswer`.
- Tests: mock `JevClient.systemone` offline; do not call the live service.

## Design

`Verifier` receives a client and explicit model identifier. `verify(state)` checks that at least one step exists and a latest result is present, then constructs JSON-compatible state containing goal, current step, latest action/result, context, and history. One system-one request asks for completion probability and a 2–4-level result-quality score. The frozen `VerificationDecision` preserves the completion probability, the quality score with its confidence and legend, plus the response model. A high or low completion probability does not itself produce `finish`, another route, or a state transition.

## Non-Goals

- Runner loop, retry, execution, or budget consumption.
- Completion threshold, policy, or state mutation.
- Persistence, trace storage, API, dashboard, or live-service integration.

## Validation Strategy

Run `uv run ruff check .`, `uv run mypy jev_router`, and `uv run pytest`. Assert exact question/request shape, one request, answer mapping, missing-result rejection before I/O, sanitized provider failures, and no mutation.

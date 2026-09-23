# Implementation Plan: Jev Client Foundation

## Summary

Implement the reusable Python Jev client for the documented `POST /v1/systemone` contract, including the `noul`, `choice`, and `score` question types. Model discovery is outside this feature's scope.

## Goals

- Provide typed request and response models for documented system-one decisions.
- Use asynchronous HTTP with an injectable transport, finite timeouts, sanitized typed errors, and no automatic retry of decisions.
- Validate outbound questions and inbound responses at the service boundary.
- Enable fully offline tests without credentials or billable API calls.
- Keep model discovery and all later V1 components outside this feature.

## Non-Goals

- Model discovery request/response implementation.
- Tool registry, router, policy engine, agent loop, verifier, API, dashboard, persistence, or eval runner.
- Live-service tests or automatic retries.

## Technical Context

- Language: Python 3.9 compatible syntax.
- HTTP: async HTTPX client with injectable transport.
- Validation: Pydantic v2 models.
- Tests: pytest and pytest-asyncio with mock HTTP transport.
- Packaging/lock: `pyproject.toml` and `uv.lock`.
- No model-discovery behavior is included in this feature; callers provide the model identifier.

## Design

The adapter in `jev_router/clients/jev.py` owns provider-specific serialization, response validation, and error conversion. The client receives a base URL, API key, and finite timeout configuration; its transport can be injected for offline tests. Typed domain structures represent question definitions and their union, and typed answer variants preserve only documented data. Secret values must never be included in errors or logs.

The system-one response contract is sourced from the TypeSafe HTTP API documentation: requests include `state`, `model`, and named `questions`; response `answers` are keyed by question ID, alongside `model` and `usage`. Noul carries a probability; Choice carries selection, probabilities, and confidence; Score carries score, legend, probabilities, and confidence. Validate constraints and consistency with the submitted question before returning answers.

## Risks and Mitigations

- Model discovery is outside this feature's scope; callers provide model names.
- Provider responses may evolve: strict boundary validation returns a sanitized schema error rather than fabricating decisions.
- Secret leakage through HTTP errors: do not embed raw response bodies, request headers, or underlying exception text in public error strings.
- Pydantic v2 support is incompatible with system Python 3.9 only if dependency resolution selects a newer unsupported release; constrain supported versions and verify lock resolution.

## Validation Strategy

Use mock transport tests to assert exact request shape, headers without exposing key values, typed parsing for all question types and mixed requests, request validation before I/O, HTTP/timeout/transport/JSON/schema failures, no retries, and secret redaction. Run formatting, static typing, and the complete offline test suite. Do not send a live request.

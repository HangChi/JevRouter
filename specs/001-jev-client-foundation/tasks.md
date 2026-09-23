# Tasks: Jev Client Foundation

## Phase 1: Setup

- [ ] T001 Create Python package metadata, supported dependency groups, and lockfile in `pyproject.toml` and `uv.lock`.
- [ ] T002 [P] Add package initializers in `jev_router/__init__.py` and `jev_router/clients/__init__.py`.
- [ ] T003 [P] Update development commands and configuration guidance in `docs/development.md`.

## Phase 2: Foundational

- [ ] T004 Define sanitized client error categories and finite timeout configuration in `jev_router/clients/jev.py`.
- [ ] T005 Define typed JSON-compatible request primitives and shared validation helpers in `jev_router/clients/jev.py`.
- [ ] T006 Configure pytest, async tests, and static-check settings in `pyproject.toml`.

## Phase 3: User Story 1 — Model discovery (blocked)

**Goal**: Discover provider models without hard-coding an account-specific identifier.

**Independent test**: Once the provider documents the endpoint and response schema, mocked responses parse into typed entries; until then, discovery is clearly unavailable without a guessed schema.

- [ ] T007 [US1] Keep model discovery unavailable and record the missing provider schema and activation criteria in `jev_router/clients/jev.py` and `specs/001-jev-client-foundation/contracts/systemone.md`.

## Phase 4: User Story 2 — Typed decision questions

**Goal**: Submit `noul`, `choice`, and `score` questions together and receive validated typed answers.

**Independent test**: Mocked requests match documented wire shape and all three answer variants round-trip, including mixed named questions; malformed or mismatched answers fail safely.

- [ ] T008 [P] [US2] Add tests for question serialization, all answer variants, mixed responses, validation-before-I/O, and sanitization in `tests/test_jev_client.py`.
- [ ] T009 [US2] Implement typed question definitions and their request constraints in `jev_router/clients/jev.py`.
- [ ] T010 [US2] Implement typed Noul, Choice, Score answers and decision response validation in `jev_router/clients/jev.py`.
- [ ] T011 [US2] Implement asynchronous `/v1/systemone` request serialization and response parsing in `jev_router/clients/jev.py`.
- [ ] T012 [US2] Convert transport, timeout, HTTP, JSON, and schema failures to sanitized typed errors without retries in `jev_router/clients/jev.py`.

## Phase 5: User Story 3 — Safe client configuration

**Goal**: Configure endpoint, credential, and timeouts outside source code while avoiding secret leakage.

**Independent test**: Valid and invalid configuration produce deterministic behavior; neither public errors nor logs reveal the configured credential.

- [ ] T013 [P] [US3] Add offline transport tests for timeout, network failures, HTTP statuses, invalid JSON/schema, no retries, and secret redaction in `tests/test_jev_client.py`.
- [ ] T014 [US3] Load and validate environment configuration without logging secret values in `jev_router/clients/jev.py`.
- [ ] T015 [US3] Document dependency installation and an explicitly model-selected client setup in `docs/development.md`.

## Phase 6: Polish

- [ ] T016 Run formatter/linter, static type checking, and the complete offline suite; correct failures in `pyproject.toml`, `jev_router/clients/jev.py`, and `tests/test_jev_client.py`.
- [ ] T017 Verify `.env` is ignored and audit generated tests/docs/errors for credentials without printing local secret contents.

## Dependencies

- T001 precedes T006 and all test execution.
- T002 and T004–T006 are foundational for user stories.
- User Story 1 is blocked on TypeSafe publishing an authoritative `/v1/models` contract; it is not a prerequisite for User Story 2 because callers supply a model identifier.
- User Story 2 and User Story 3 can be implemented as independently testable increments after foundation; share the client module carefully.
- T016–T017 follow implementation.

## Parallel opportunities

- After T001: T002 and T003 can proceed independently.
- After foundational setup: T008 can be developed alongside T009/T010 if interfaces are coordinated; T013 can follow the same mock transport contract.
- T007 is informational and can be completed independently of `/v1/systemone` work.

## Implementation strategy

Deliver the usable `/v1/systemone` client as the MVP and explicitly report `/v1/models` as blocked. Validate with offline mocks, then finalize configuration and docs. Do not expand into later V1 stages.

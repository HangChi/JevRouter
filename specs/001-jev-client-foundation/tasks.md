# Tasks: Jev Client Foundation

## Phase 1: Setup

- [x] T001 Create Python package metadata, supported dependency groups, and lockfile in `pyproject.toml` and `uv.lock`.
- [x] T002 [P] Add package initializers in `jev_router/__init__.py` and `jev_router/clients/__init__.py`.
- [x] T003 [P] Update development commands and configuration guidance in `docs/development.md`.

## Phase 2: Foundational

- [x] T004 Define sanitized client error categories and finite timeout configuration in `jev_router/clients/jev.py`.
- [x] T005 Define typed JSON-compatible request primitives and shared validation helpers in `jev_router/clients/jev.py`.
- [x] T006 Configure pytest, async tests, and static-check settings in `pyproject.toml`.

## Phase 3: User Story 1 — Typed decision questions

**Goal**: Submit `noul`, `choice`, and `score` questions together and receive validated typed answers.

**Independent test**: Mocked requests match documented wire shape and all three answer variants round-trip, including mixed named questions; malformed or mismatched answers fail safely.

- [x] T007 [US1] Model discovery is outside this feature's scope; callers provide the model identifier.
- [x] T008 [P] [US1] Add tests for question serialization, all answer variants, mixed responses, validation-before-I/O, and sanitization in `tests/test_jev_client.py`.
- [x] T009 [US1] Implement typed question definitions and their request constraints in `jev_router/clients/jev.py`.
- [x] T010 [US1] Implement typed Noul, Choice, Score answers and decision response validation in `jev_router/clients/jev.py`.
- [x] T011 [US1] Implement asynchronous `/v1/systemone` request serialization and response parsing in `jev_router/clients/jev.py`.
- [x] T012 [US1] Convert transport, timeout, HTTP, JSON, and schema failures to sanitized typed errors without retries in `jev_router/clients/jev.py`.

## Phase 4: User Story 2 — Safe client configuration

**Goal**: Configure endpoint, credential, and timeouts outside source code while avoiding secret leakage.

**Independent test**: Valid and invalid configuration produce deterministic behavior; neither public errors nor logs reveal the configured credential.

- [x] T013 [P] [US2] Add offline transport tests for timeout, network failures, HTTP statuses, invalid JSON/schema, no retries, and secret redaction in `tests/test_jev_client.py`.
- [x] T014 [US2] Load and validate environment configuration without logging secret values in `jev_router/clients/jev.py`.
- [x] T015 [US2] Document dependency installation and an explicitly model-selected client setup in `docs/development.md`.

## Phase 5: Polish

- [x] T016 Run formatter/linter, static type checking, and the complete offline suite; correct failures in `pyproject.toml`, `jev_router/clients/jev.py`, and `tests/test_jev_client.py`.
- [x] T017 Verify `.env` ignore rules from `.gitignore` and audit generated tests/docs/errors for credentials without printing local secret contents. This workspace is not a Git repository, so Git-based ignore verification is unavailable.

## Dependencies

- T001 precedes T006 and all test execution.
- T002 and T004–T006 are foundational for user stories.
- User Story 1 and User Story 2 are independently testable after the foundation; they share the client module carefully.
- T016–T017 follow implementation.

## Parallel opportunities

- After T001: T002 and T003 can proceed independently.
- After foundational setup: tests can be developed alongside the corresponding client code if interfaces are coordinated.

## Implementation strategy

Deliver the usable `/v1/systemone` client as the MVP. Callers supply model identifiers; model discovery and later V1 stages are outside this feature. Validate with offline mocks, then finalize configuration and docs.

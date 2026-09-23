# Feature Specification: API HTTP Boundary

**Feature Branch**: `009-api-http`
**Status**: Complete

## Goal

Expose the Runner and the trace store over HTTP so a client can start a task, watch it, answer a confirmation prompt, supply requested input, and read the resulting traces. The API layer adds no agent behaviour; it only carries requests and responses.

## User Stories

### US1 - Start a task and watch it

As a client developer, I need to submit a goal and poll its progress without holding a connection open.

Acceptance scenarios:
1. `POST /tasks` accepts a goal and returns `202` with a task id and initial status.
2. `GET /tasks/{id}` reports the live or terminal status, step count, diagnostic and any pending prompt.
3. `GET /tasks/{id}/traces` returns the traces written so far, including while the run is still going.
4. An unknown task id returns `404` on every task-scoped route.

### US2 - Answer a confirmation prompt

As a client developer, I need to approve or deny a pending action with its resolved arguments visible.

Acceptance scenarios:
1. A `write` or `external` risk action pauses the run in `awaiting_confirmation` and reports the action and arguments.
2. `POST /tasks/{id}/confirm` with `approved: true` resumes the run and performs the action.
3. `approved: false` stops the run at `needs_confirmation` with no side effect.
4. Confirming a task that is not awaiting confirmation returns `409`.

### US3 - Supply requested input

As a client developer, I need to answer an `ask_user` prompt.

Acceptance scenarios:
1. The run pauses in `awaiting_input` and reports the question.
2. `POST /tasks/{id}/input` resumes the run with the supplied answer.
3. Supplying input when nothing is pending returns `409`.

### US4 - Trust the boundary

As an operator, I need the API to reject malformed input and never disclose a credential.

Acceptance scenarios:
1. A blank or oversized goal, an unknown field, or a blank answer is rejected with `422`.
2. No response body contains the provider credential.
3. Configuration is validated at startup, so a misconfigured deployment refuses to serve.

## Requirements

- **FR-001**: Provide `POST /tasks`, `GET /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/traces`, `POST /tasks/{id}/confirm` and `POST /tasks/{id}/input`.
- **FR-002**: Run each task as a background coroutine; requests never block on a run.
- **FR-003**: Resolve confirmation and user input through futures so a run survives across requests.
- **FR-004**: Report a live status (`running`, `awaiting_confirmation`, `awaiting_input`) distinct from the terminal `RunStatus`.
- **FR-005**: Validate every request body with a strict schema and reject unknown fields.
- **FR-006**: Map unknown tasks to `404`, a wrong-phase prompt to `409`, and invalid bodies to `422`.
- **FR-007**: Validate all configuration at startup and refuse to serve when it is invalid.
- **FR-008**: Never return the provider credential in any response.
- **FR-009**: Leave the core package untouched; the API layer only consumes `Runner`, `TraceStore` and the typed decisions.
- **FR-010**: Offline tests cover every endpoint, every error mapping, the confirmation and input flows, and the credential guarantee.

## Success Criteria

- A submitted task reaches a terminal status without any request blocking on it.
- A confirmation prompt carries the resolved arguments and resumes on approval.
- No credential appears in any response body.
- Ruff, strict mypy and the full offline test suite pass, and the app boots under uvicorn.

## Non-Goals

- Authentication, authorization, rate limiting or multi-tenancy.
- The Web dashboard, streaming or server-sent events.
- Task cancellation, retry or resumption after a process restart.
- Migrating in-flight runs when a store is replaced.
- Changing the core package's contracts.

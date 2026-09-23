# Tasks: API HTTP Boundary

## Phase 1: Configuration and Schemas

- [x] T001 Add `fastapi` and `uvicorn` as runtime dependencies with upper bounds.
- [x] T002 Define the frozen `Settings` model with environment loading and startup validation in `apps/api/config.py`.
- [x] T003 Define strict request/response models and the live-status constants in `apps/api/schemas.py`.
- [x] T004 Reject blank goals at the schema boundary rather than starting a doomed run.

## Phase 2: Service and Routes

- [x] T005 Implement `TaskService` with an in-memory run registry and future-based prompts.
- [x] T006 Bind confirmation and input requests to a task id through a per-run handler adapter.
- [x] T007 Surface the live status and pending prompt on the run handle.
- [x] T008 Persist a finished run and keep its terminal status even if persistence fails.
- [x] T009 Implement the six routes with `404`/`409`/`422`/`400` error mapping.
- [x] T010 Provide `default_registry(settings)` and close the store only when the app owns it.

## Phase 3: Tests and Documentation

- [x] T011 Extract the shared offline doubles into `tests/support.py` and reuse them across test modules.
- [x] T012 Test every endpoint, error mapping and list ordering in `tests/test_api.py`.
- [x] T013 Test the confirmation and input round trips, including denial and wrong-phase calls.
- [x] T014 Test that no response body carries the credential.
- [x] T015 Test startup configuration validation.
- [x] T016 Document scope, data model and phase boundaries in this spec directory.
- [x] T017 Update architecture and development documentation for the API layer.
- [x] T018 Run Ruff, strict mypy and full offline pytest; boot the app under uvicorn and exercise it with curl.

## Dependencies

T001–T004 precede T005–T010. T011–T018 follow implementation and tests.

## Completion Criteria

All tasks are checked only after implementation and validation. The API layer carries requests and responses only; it adds no agent behaviour and changes no core contract.

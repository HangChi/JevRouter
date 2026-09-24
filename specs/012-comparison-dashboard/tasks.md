# Tasks: Comparison Dashboard

## Phase 1: Persistence and HTTP boundary

- [x] T001 Extend `apps/api/storage.py` with `eval_runs` and `eval_case_results`, bump `SCHEMA_VERSION` to 2, and implement `record_eval_run`, `list_eval_runs` and `load_eval_run` using the existing envelope encode/decode and upsert idempotence; cover round-trip, re-recording the same id, and a version-1 database still opening.
- [x] T002 Add the strict payload and view models to `apps/api/schemas.py` for recording and reading an eval run.
- [x] T003 Add `POST /evals`, `GET /evals` and `GET /evals/{run_id}` to `apps/api/app.py` with the existing error mapping (`404` unknown run, `422` invalid body, `400` bad limit), and cover them in `tests/test_api.py`.

## Phase 2: CLI bridge

- [x] T004 Add `--api URL` to `evals/cli.py`: after a run finishes, post the report to `POST /evals` using the API's own payload models, reporting a non-2xx answer as a failure with the API's message.

## Phase 3: Web dashboard

- [x] T005 Mirror the eval transport types in `apps/web/src/lib/types.ts`.
- [x] T006 Add `listEvalRuns` and `getEvalRun` to `apps/web/src/lib/api.ts` and cover them with a stubbed fetch.
- [x] T007 Add the eval view model to `apps/web/src/lib/viewModel.ts`: aggregate cards per mode, agreement tone, per-case comparison rows, and formatting for rates, durations and token counts; unit-test it including absent metrics and one-sided runs.
- [x] T008 Build `apps/web/src/app/evals/page.tsx`: the run list with one card set per run, the API-unavailable notice and the empty state.
- [x] T009 Build `apps/web/src/app/evals/[runId]/page.tsx`: the per-case comparison table with expected action, both modes' actions, agreement, latencies, tokens and errors, plus the not-found page for an unknown run.
- [x] T010 Add the evals link to the dashboard header.

## Phase 4: Checks, verification and documentation

- [x] T011 Run `tsc --noEmit`, vitest, eslint and `next build` in `apps/web`; fix everything they report.
- [x] T012 Verify end to end: boot `apps.api` under uvicorn with a temporary database, record a seeded compare run through `POST /evals` driven by curl, read it back through `GET /evals/{run_id}`, and render both dashboard pages against that API with curl.
- [x] T013 Update `README.md`, `docs/development.md`, `docs/architecture.md` and `apps/web/README.md` for the eval endpoints and pages; record the new schema version.
- [x] T014 Write this spec directory's `data-model.md` and `quickstart.md`, then run the full project checks (ruff, strict mypy over `jev_router apps evals`, pytest).

## Dependencies

T001 precedes T002/T003. T003 precedes T004. T005–T007 precede T008/T009. T010 is independent. T011–T014 follow implementation.

## Completion Criteria

All tasks are checked only after implementation and validation. No metric definition changes in this phase, and `evals/` still imports nothing from `apps/` except the CLI's payload models for the `--api` bridge.

# Tasks: Web Trace Dashboard

## Phase 1: Scaffold and transport

- [x] T001 Scaffold `apps/web/` as a Next.js App Router project with TypeScript, Tailwind and an import alias; record the Node toolchain expectation in its README.
- [x] T002 Mirror `apps/api/schemas.py` in `src/lib/types.ts` and document the mirror.
- [x] T003 Add `src/lib/thresholds.ts` with the display-only mirror of the core's MVP thresholds.
- [x] T004 Implement `src/lib/api.ts` with injectable fetch, `ApiError` and `ApiUnavailableError`, and `API_UPSTREAM_URL` resolution.
- [x] T005 Add `.env.example` recording `API_UPSTREAM_URL` and nothing else.

## Phase 2: View model

- [x] T006 Implement `statusTone`, `policyBranch`, `probabilityMeters`, `scoreReadouts`, `verificationReadout` and `decisionChain` in `src/lib/viewModel.ts`.
- [x] T007 Implement the formatters `formatDuration`, `formatProbability` and `formatScore`.
- [x] T008 Unit-test the view model, including missing fields, unknown statuses and unknown policy outcomes.
- [x] T009 Unit-test the API client against a stubbed fetch: paths, methods, bodies, `404`/`409` mapping and the unavailable-upstream case.

## Phase 3: Pages and components

- [x] T010 Build the task list page with the submit form and the API-unavailable notice.
- [x] T011 Build the task detail page: header, pending prompt, decision chain and one card per step.
- [x] T012 Render probability meters, score readouts and the verification readout, with "—" for absent fields.
- [x] T013 Add `<LiveRefresh>` so a live task refreshes on an interval and stops when terminal.
- [x] T014 Wire the submit, confirm and provide-input server actions, including the `409` notice.
- [x] T015 Add the not-found page for an unknown task id.

## Phase 4: Checks and documentation

- [x] T016 Run `tsc --noEmit`, the vitest suite and `next build`; fix everything they report.
- [x] T017 Boot `apps/api` under uvicorn with a stubbed Jev client and a temporary database, then exercise submit, confirm and trace reading through the dashboard with curl.
- [x] T018 Write `apps/web/README.md` covering setup, configuration and the checks.
- [x] T019 Update `README.md`, `docs/architecture.md` and `docs/development.md` for the web layer.
- [x] T020 Document scope, data model and phase boundaries in this spec directory, and run the full project checks.

## Dependencies

T001–T005 precede T006–T015. T016–T020 follow implementation.

## Completion Criteria

All tasks are checked only after implementation and validation. No file under `jev_router/` or `apps/api/` changes in this phase.

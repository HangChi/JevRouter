# Tasks: Decision Router

## Phase 1: Router Contract

- [x] T001 Define the action and risk question contract and immutable decision result in `jev_router/router.py`.
- [x] T002 Implement one-request async routing over trusted registered tools and fixed control actions.
- [x] T003 Export `Router` and `RouteDecision` from the package.

## Phase 2: Tests and Documentation

- [x] T004 Test request shape, risk legend, result mapping, empty registry, typed errors, and no execution in `tests/test_router.py`.
- [x] T005 Document scope, data model, offline use, and phase boundaries in this spec directory.
- [x] T006 Update architecture and development documentation for Router's recommendation-only role.
- [x] T007 Run Ruff, strict mypy, and full offline pytest; review the authority boundary.

## Dependencies

T001 precedes T002–T004. T006–T007 follow implementation and tests.

## Completion Criteria

All tasks are checked only after implementation and validation. The Router does not authorize or execute tool actions.

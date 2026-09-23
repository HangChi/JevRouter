# Tasks: Tool Registry and MVP Tools

## Phase 1: Foundation

- [x] T001 Define the tool protocol, risk levels, and structured result in `jev_router/tools/base.py`.
- [x] T002 [P] Implement trusted in-memory registry registration, lookup, and dispatch in `jev_router/tools/registry.py`.
- [x] T003 [P] Add public exports in `jev_router/tools/__init__.py`.

## Phase 2: MVP Tools

- [x] T004 Implement bounded arithmetic evaluation with an AST allowlist in `jev_router/tools/calculator.py`.
- [x] T005 Implement injected local knowledge search and bounded excerpts in `jev_router/tools/knowledge_search.py`.
- [x] T006 Implement fixture-only mock web search in `jev_router/tools/web_search.py`.
- [x] T007 Implement root-constrained file writing, size limits, symlink containment, and default no-overwrite in `jev_router/tools/write_file.py`.
- [x] T008 Implement validated local-only mock email in `jev_router/tools/mock_email.py`.

## Phase 3: Tests and Documentation

- [x] T009 Cover registry and MVP tool success/error boundaries in `tests/test_tools.py`.
- [x] T010 Document tool usage and security boundaries in `docs/development.md` and `docs/security.md`.
- [x] T011 Define phase scope, architecture, data model, and offline quickstart in this spec directory.
- [x] T012 Run Ruff, strict mypy, and the full offline pytest suite; all checks pass.
- [x] T013 Review filesystem boundary assumptions and verify no live network/service behavior is introduced. The configured root must be protected from hostile concurrent symlink replacement.

## Dependencies

T001 precedes T002–T008. Each tool implementation precedes its boundary tests. T012–T013 follow implementation and documentation.

## Completion Criteria

All tasks are checked only after their implementation and validation are complete. No router, policy engine, runner, API, dashboard, persistence, or live integration is included in this phase.

# Implementation Plan: Comparison Dashboard

## Design Decisions

### 1. Eval results live in the same store as traces

The store already owns versioned persistence, upsert idempotence and the "refuse what you cannot read" rule, so eval runs follow it rather than inventing a second storage mechanism. Two new tables:

```text
eval_runs           one row per recorded run: run_id, mode, created_at, case_count, metrics payload
eval_case_results   one row per (run_id, case_id, mode): the case outcome payload
```

`SCHEMA_VERSION` moves 1 → 2. The bump is additive, and the store already refuses only *newer* databases, so an existing phase-8 database opens unchanged and gains the tables. Every JSON column keeps the `{"version": 1, "data": ...}` envelope and the same `_encode`/`_decode` pair, so a payload this build cannot read fails loudly instead of silently mis-reading a metric.

### 2. The payload models are API-owned; the CLI imports them

`apps/api/schemas.py` defines the strict request/response models (`RecordEvalRunRequest` and friends). `evals/cli.py` — the one module in `evals/` allowed to cross the layer boundary — imports them to build the `--api` POST body, which makes it impossible for the CLI to send a body the API would reject. The eval library itself (`cases`, `runner`, `metrics`, `llm_router`, `registry`) still imports nothing from `apps/`, keeping the dependency direction in `docs/development.md` intact.

### 3. The web layer mirrors, as before

`src/lib/types.ts` hand-mirrors the new transport models, `src/lib/api.ts` gains `listEvalRuns`/`getEvalRun` with the same injectable-fetch and error mapping, and `src/lib/viewModel.ts` gains the pure functions that turn a run into cards and rows. Components stay layout-only. Absent metrics render as "—", matching the existing rule that `NULL` and a real `0` are different facts.

### 4. Two pages, no new navigation machinery

`/evals` lists runs with the aggregate cards of each run's metrics; `/evals/[runId]` renders the per-case comparison table. The header gains one link. Polling is deliberately absent: an eval run is a finished record, not a live process.

## File Layout

```text
apps/api/storage.py      + eval_runs / eval_case_results, record/list/load, SCHEMA_VERSION 2
apps/api/schemas.py      + RecordEvalRunRequest, payload models, read views
apps/api/app.py          + POST /evals, GET /evals, GET /evals/{run_id}
evals/cli.py             + --api URL (posts the finished report)
apps/web/src/lib/types.ts     + eval mirrors
apps/web/src/lib/api.ts       + listEvalRuns, getEvalRun
apps/web/src/lib/viewModel.ts + eval card/row view model
apps/web/src/app/evals/page.tsx
apps/web/src/app/evals/[runId]/page.tsx
tests/test_storage.py    + eval run round-trip, idempotence, versioned payload refusal
tests/test_api.py        + endpoint schema, 404/422 mapping, round-trip through the service
apps/web/src/lib/viewModel.test.ts, api.test.ts + eval coverage
```

## Testing Strategy

- Storage: temporary SQLite file, round-trip a recorded run, re-record the same id, refuse a tampered payload envelope.
- API: `TestClient` with an injected store; assert status codes and that the served view equals what was posted.
- Web: vitest over the new view-model functions and client methods with a stubbed fetch, then `tsc --noEmit`, lint and `next build`.

## Risks

- **Schema version bump**: an older database must keep working. Mitigated by the additive change and covered by opening a version-1 database in a test.
- **Report size**: 50 cases × two modes is a few hundred rows per run; listing stays bounded by `limit`, and the detail page loads one run only.

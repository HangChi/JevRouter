# Data Model: Comparison Dashboard

## Tables (`apps/api/storage.py`)

```text
eval_runs (
    run_id     TEXT PRIMARY KEY,
    mode       TEXT NOT NULL,      -- jev | llm | compare
    created_at TEXT NOT NULL,      -- UTC ISO-8601 from the eval report
    metrics    TEXT NOT NULL       -- {"version": 1, "data": ComparisonMetricsPayload}
)

eval_case_results (
    run_id  TEXT NOT NULL,
    case_id TEXT NOT NULL,
    mode    TEXT NOT NULL,         -- jev | llm
    payload TEXT NOT NULL,         -- {"version": 1, "data": EvalCaseOutcomePayload}
    PRIMARY KEY (run_id, case_id, mode),
    FOREIGN KEY (run_id) REFERENCES eval_runs (run_id) ON DELETE CASCADE
)
```

`SCHEMA_VERSION` moves 1 → 2. The change is additive and the store only refuses databases *newer* than the build, so an existing phase-8 database opens unchanged and gains the tables; a test covers exactly that.

Both payload columns use the store's existing `_encode`/`_decode` pair. `_encode` degrades values JSON cannot hold, but a pydantic model is not one of them — `jsonable` would refuse a `BaseModel` and silently degrade it to `{"__unserializable__": ...}` — so the models are dumped to plain dicts with `model_dump(mode="json")` first.

## Wire models (`apps/api/schemas.py`)

`RecordEvalRunRequest` is the POST body: `run_id`, `mode`, `created_at`, `outcomes`, `metrics`. It carries no `case_count`: that is derived from the distinct case ids, so a report cannot claim a count its own rows contradict.

Validation beyond field ranges:

- `mode` must be one of `jev`, `llm`, `compare`.
- Every outcome's `mode` must belong to the run's mode (`jev` → jev rows only, `compare` → both).
- A compare run must pair every case across both routers: the jev case-id set must equal the llm set.
- Rates are constrained to `[0, 1]`, counts and latencies to non-negative.

`ComparisonMetricsPayload` holds `jev`, `llm`, `agreement_count`, `compared_count`, `agreement_rate`, `disagreement_case_ids`. The policy fields inside `ModeMetricsPayload` are `None` for the baseline. `agreement_rate` is `None` unless both modes answered at least one case, and the API does not recompute it: the rates travel with the data so a stored report stays interpretable without this build's arithmetic.

## Read views

`EvalRunSummary` (list row: run id, mode, created_at, case count) and `EvalRunView` (summary + metrics + outcomes). `case_count` is the number of distinct case ids, so a 50-case compare run reports 50 rather than 100 rows.

`load_eval_run` orders rows by `(case_id, mode)`, which puts both routers' rows for one case next to each other and lines two runs of the same case set up row for row.

## CLI bridge

`--api URL` posts `report_to_dict(report)["data"]` — the envelope's payload, not the envelope — to `POST /evals`. A refusal is reported with the API's own message and exits `3` (`EXIT_DELIVERY`), distinct from a case error (`1`) and a configuration problem (`2`).

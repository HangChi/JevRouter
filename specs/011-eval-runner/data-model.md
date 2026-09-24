# Data Model: Eval Runner and LLM Baseline

## `EvalCase` (`evals/cases.py`)

Strict, frozen pydantic model. One routing expectation.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `str` | kebab-case, unique within the file, max 64 |
| `goal` | `str` | the user goal, 1–2000 chars |
| `expected_action` | `str` | the action considered correct for the first step |
| `allowed_actions` | `tuple[str, ...]` | non-empty, no repeats, must contain `expected_action` |
| `requires_confirmation` | `bool` | whether the Policy Engine is expected to ask before acting |
| `context` | `dict \| None` | optional task context handed to the routing state |
| `notes` | `str \| None` | why the case expects what it expects |

The file is `{"version": 1, "cases": [...]}`. `load_cases` refuses an unknown version, a malformed entry, a duplicate id and an empty list; a silently dropped case would change every reported rate.

`requires_confirmation` is true exactly for `write_file` and `send_mock_email`, mirroring the `write`/`external` risk rule the Runner enforces at execution time. A test asserts this against the committed file.

## `RouteDecision` addition (`jev_router/router.py`)

```text
input_tokens: int | None = None
output_tokens: int | None = None
```

Populated from `DecisionResponse.usage`. Optional and additive: nothing in the run path reads them, and the comparison metrics need them. `None` rather than `0` when absent, because "no usage reported" and "zero tokens" are different facts.

## `LLMCompletion` / `LLMRouteDecision`

`LLMCompletion` (`jev_router/clients/llm.py`): `text`, `model`, `input_tokens`, `output_tokens`.

`LLMRouteDecision` (`evals/llm_router.py`): `action`, `reason`, `model`, `latency_ms`, `input_tokens`, `output_tokens`. No probabilities — the baseline has none, and the comparison must not invent them.

## `CaseOutcome` (`evals/runner.py`)

One row per (case, router). `mode` is `"jev"` or `"llm"`, so a compare run stores both rows for a case and the aggregation pairs them by `case_id`.

| Field | Meaning |
| --- | --- |
| `action` | the chosen action, or `None` when the router errored |
| `matched_expected` / `matched_allowed` | equals `expected_action` / is in `allowed_actions` |
| `succeeded` | `matched_allowed` **and** the policy's confirmation decision matches `requires_confirmation` |
| `policy_outcome` | the Policy Engine's outcome; `None` for the baseline |
| `escalated` | outcome in `{ask_confirmation, delegate_to_llm, ask_user}`; `None` for the baseline |
| `confirmation_requested` | outcome is `ask_confirmation`; `None` for the baseline |
| `latency_ms` | wall-clock around the route call, measured even on failure |
| `input_tokens` / `output_tokens` | provider usage; `None` when the call failed |
| `error` | category-tagged message, or `None` |

`finish` is completion and `reject` is failure, so neither counts as an escalation.

## `ModeMetrics` / `ComparisonMetrics` (`evals/metrics.py`)

`ModeMetrics` carries counts and derived rates (`expected_match_rate`, `allowed_match_rate`, `success_rate`, `error_rate`, `escalation_rate`). Policy fields are `None` for the baseline. `latency` is `LatencyStats(mean_ms, p50_ms, p95_ms, max_ms)` with nearest-rank percentiles; `input_tokens`/`output_tokens` are `TokenStats(mean, total)` or `None` when no case reported usage.

`ComparisonMetrics` adds `jev`, `llm`, `agreement_count`, `compared_count`, `disagreement_case_ids` and a derived `agreement_rate`. The rate is `None` unless both modes answered at least one case, because "0%" and "never compared" are different statements. Agreement is measured over cases where **both** routers produced an action.

## `EvalReport` and the wire envelope

`EvalReport` = `run_id`, `mode`, `created_at` (UTC ISO-8601), `outcomes`, `metrics`.

`evals/report.py` serializes it as `{"version": 1, "data": {...}}` with the rates written out rather than derived, so a stored report stays interpretable without this build's arithmetic. The `data` object is what `POST /evals` accepts in phase 12.

## Storage (phase 12)

```text
eval_runs           run_id, mode, created_at, case_count, metrics payload
eval_case_results   run_id, case_id, mode, outcome payload
```

Both payload columns use the store's existing `{"version": 1, "data": ...}` envelope and `_encode`/`_decode` pair; `SCHEMA_VERSION` moves to 2 additively.

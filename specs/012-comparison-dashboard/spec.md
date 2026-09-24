# Feature Specification: Comparison Dashboard

**Feature Branch**: `012-comparison-dashboard`
**Status**: Complete

## Goal

Close the loop `doc.md` describes in its final section: eval runs become durable records the HTTP boundary serves, and the dashboard renders the Jev-vs-LLM comparison — per-case decisions, latencies and token counts side by side, plus the aggregate agreement, match, escalation and success rates. This phase adds no routing behaviour; it persists and displays what phase 11's runner already produces.

## Scope

In scope:

- `apps/api/storage.py`: `eval_runs` and `eval_case_results` tables following the store's existing conventions (schema version, versioned JSON envelopes, upsert idempotence), with `record_eval_run`, `list_eval_runs` and `load_eval_run`.
- `apps/api/schemas.py`: strict payload models for a recorded run plus read views.
- `apps/api/app.py`: `POST /evals`, `GET /evals`, `GET /evals/{run_id}` with the existing error mapping.
- `evals/cli.py`: an `--api` option that posts a finished report to the running API.
- `apps/web`: the mirror types, client methods, view model functions and the two pages — a run list with aggregate cards, and a run detail with the per-case comparison table.

Out of scope: changing any metric definition (phase 11 owns that), rerunning evals from the browser, and any write path other than recording a finished report.

## User Stories

### US1 - Keep eval runs

As the project owner, I need an eval run to survive the process that produced it, so a threshold decision can cite a specific run instead of a terminal scrollback.

Acceptance scenarios:

1. `POST /evals` with a complete report stores it and answers with the run id.
2. Recording the same run id twice does not duplicate rows.
3. `GET /evals` lists runs newest first with mode, timestamp and case count; `GET /evals/{run_id}` returns the metrics and every per-case outcome.
4. An unknown run id answers `404`; a body failing the strict schema answers `422`.

### US2 - See the comparison at a glance

As the project owner, I need the dashboard to show, for the newest runs, the agreement rate and each mode's match, escalation, confirmation and success rates with latency and token summaries, so I can tell whether a change moved the numbers.

Acceptance scenarios:

1. The eval list page shows one card per aggregate metric with the mode it belongs to.
2. Latency is rendered with the existing duration formatter; token counts as plain numbers.
3. A metric that a mode cannot produce (the LLM baseline has no policy outcome) renders as absent, not as zero.
4. An unreachable API shows the same notice the run list uses.

### US3 - Read one run case by case

As the project owner, I need a table of every case with both routers' actions, whether they agreed, and each side's latency and tokens, so a disagreement can be traced back to the goal that caused it.

Acceptance scenarios:

1. Each row shows the case id and goal, the expected action, each mode's chosen action, agreement, latency and tokens.
2. A case where a router errored shows the error instead of an action.
3. Cases where only one mode ran render that side and mark the other absent.
4. The rows are ordered by case id so two runs of the same case set line up.

## Non-Goals

- No eval execution from the browser; runs stay a CLI act with explicit credentials.
- No charts beyond the existing meter/readout vocabulary, unless a table cannot carry the number.
- No retention or deletion policy for stored runs.

## Dependencies

- Phase 11: the report shape (`CaseOutcome`, `ModeMetrics`, `ComparisonMetrics`) this phase persists and renders.

# Data Model: Web Trace Dashboard

## Transport types

`src/lib/types.ts` hand-mirrors the response models of `apps/api/schemas.py`. It is a copy, not a generated client: the API is the source of truth and the mirror must be updated when a field changes there. Optionality matches the API — a field the API may omit is `| null` here, because the store returns `NULL` for a probability that was never recorded.

| Type | Fields |
| --- | --- |
| `TaskSummary` | `task_id`, `goal`, `status`, `step` |
| `TaskView` | `TaskSummary` + `diagnostic`, `pending_confirmation`, `pending_input` |
| `PendingConfirmationView` | `action`, `arguments`, `step` |
| `PendingInputView` | `question`, `step` |
| `TraceView` | `step`, `action`, `policy_outcome`, `policy_reason`, `executed`, `result`, `route_confidence`, `route_risk`, `requires_confirmation`, `needs_reasoning`, `confirmed`, `arguments`, `completion_probability`, `quality_score`, `state_snapshot`, `duration_ms` |
| `TaskListResponse` | `tasks: TaskSummary[]` |
| `TraceListResponse` | `task_id`, `traces: TraceView[]` |

`arguments`, `result` and `state_snapshot` are JSON of unknown shape, so they are typed as `unknown` and rendered through a JSON viewer rather than a fixed model. `TraceView` carries no `task_id`; the task id comes from the enclosing response.

## Statuses

Two vocabularies, exactly as in phase 9:

- Live: `running`, `awaiting_confirmation`, `awaiting_input`.
- Terminal: `completed`, `needs_user_input`, `needs_confirmation`, `rejected`, `budget_exhausted`, `failed`.

`statusTone()` maps each to one of five presentation tones: `live`, `blocked`, `good`, `bad` and `neutral`. `blocked` covers both live blocking states and the terminal states that ended because a human was needed; `neutral` is for a control outcome that is neither good nor bad. Anything unrecognized maps to `bad` rather than being rendered as if it were fine. A status is never carried by colour alone — the badge spells the transported string out beside its dot.

## Thresholds (display only)

`src/lib/thresholds.ts` mirrors the MVP thresholds of `jev_router/policy.py`:

| Constant | Value | Used for |
| --- | --- | --- |
| `ROUTE_CONFIDENCE_THRESHOLD` | `0.75` | meter mark on `route_confidence` |
| `CONFIRMATION_THRESHOLD` | `0.75` | meter mark on `requires_confirmation` |
| `REASONING_THRESHOLD` | `0.70` | meter mark on `needs_reasoning` |
| `RISK_THRESHOLD` | `2.5` | comparison value for `route_risk` |
| `COMPLETION_THRESHOLD` | `0.75` | meter mark on `completion_probability` |

These exist only to draw marks. The decision the dashboard reports is the API's `policy_outcome`; if a threshold here drifts from the core package, the marks are wrong but the reported outcome is still right. They live in one module with that warning so the drift has one place to be fixed.

## Score scales

`ScoreAnswer.score` is a finite float the core package does not normalize (`jev_router/clients/jev.py` only checks finiteness). The two scores that reach the dashboard are therefore shown as raw numbers with the threshold beside them:

- `route_risk` — scored over the five risk levels the Router submits, so a 0-based index spans `0`–`4` and the `2.5` threshold sits between "meaningful but reversible" and "external or consequential".
- `quality_score` — scored over the verifier's four-level legend, so a 0-based index spans `0`–`3`.

`riskLevel()` and `qualityLevel()` turn a score into a level index for the level strip, assuming that 0-based index scale. The strip is captioned with the scale itself (`scale 0–4`, `scale 0–3`) rather than with a level number, so the assumption is stated instead of asserted. No score is ever drawn as a 0–1 probability bar.

## View model

`src/lib/viewModel.ts` holds pure functions over the transport types, with no React and no I/O, so they can be unit-tested directly:

- `statusTone(status)` → tone key; `isLiveStatus(status)` → whether polling should continue.
- `policyBranch(trace)` → which branch a step took: `executed`, `denied`, `approved_failed`, `rejected`, `delegated`, `asked`, `finished`, `not_executed`, `unknown`. Derived from `policy_outcome`, `executed` and `confirmed`; an unknown outcome yields `unknown` rather than a guess. `approved_failed` is the case the raw fields make visible: a confirmation was granted and the tool still did not run.
- `probabilityMeters(trace)` → the 0–1 routing meters with value, threshold, direction and whether the threshold was crossed.
- `completionMeter(trace)` → the completion probability as a meter, or `null` for a step that was never verified.
- `scoreReadouts(trace)` → `route_risk` and `quality_score` with their thresholds, level index and level count.
- `verificationReadout(trace)` → completion probability and quality score, or `null` when the step has no verification.
- `decisionChain(traces)` → one node per step in step order, carrying action, outcome tone and branch.
- `outcomeTone`, `outcomeLabel`, `branchLabel` → the presentation of a policy outcome and a branch.
- `formatDuration(ms)`, `formatProbability(value)`, `formatScore(value)`.

## Step counts

The two counts a run can be described by are not the same number. `TaskView.step`
is the state's step counter, which the API only records once a run finishes;
`traces.length` is the number of steps the dashboard actually has records for,
which is larger whenever a step ended in `reject`, `ask_user` or `finish` without
advancing the state.

The list shows the API's count and only for a terminal run — a live handle
reports `0`, which would read as "no steps taken". The detail page counts the
steps it renders and labels them "recorded". Neither number is invented, and
neither is presented as the other.

## Visual encoding

Colour was chosen after the form, and the palette was validated rather than
eyeballed. The rules the dashboard holds itself to:

- **Meters** carry a single ratio against a limit. The fill is the accent hue
  while the signal is inside its band and the warning hue once it has crossed
  into the side the Policy Engine acts on; the unfilled track is a lighter step
  of the same ramp, so the state reads across the whole bar. The threshold is a
  solid hairline tick with its value printed beside the meter, and the value
  itself is always printed — a mark is never the only way to read a number.
- **Level strips** use an ordinal single-hue ramp (blue, light to dark), because
  the levels are ordered rather than nominal. Both ramps pass the ordinal
  checks: monotone lightness, visible step gaps, and a light end that clears
  2:1 against the surface.
- **Status colour** is reserved for state and always paired with the transported
  status string, so nothing is carried by hue alone. The palette's `warning` and
  `serious` steps sit below 3:1 on the light surface by design; `serious` is
  simply not used, and the labels are the relief for `warning`.
- **Text wears text tokens.** Values, labels and captions use the ink tokens; the
  colour lives in the mark beside them.
- **Dark mode is selected, not flipped.** Both modes have their own steps from
  the same ramps, chosen against their own surface.
- No dual axes, no value ramp on nominal categories, no dashed gridlines, and no
  number printed on every mark.

## API client

`src/lib/api.ts` talks to `API_UPSTREAM_URL` (default `http://127.0.0.1:8000`) and is server-only. Every function takes an optional fetch implementation so tests can stub it; production uses the global fetch. Failures are typed: `ApiError` carries the upstream status and message for `4xx`/`5xx`, and `ApiUnavailableError` carries the upstream URL when the connection itself fails. The distinction matters because a `404` means "no such task" while a connection failure means "the dashboard is pointed at the wrong place".

## Routes

| Route | Renders |
| --- | --- |
| `/` | task list, newest first, plus the submit form |
| `/tasks/[taskId]` | task header, pending prompt, decision chain, step cards |

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_UPSTREAM_URL` | `http://127.0.0.1:8000` | base URL of the `apps/api` server |

The web app reads no other configuration and holds no credential. `.env.example` in `apps/web/` records the one variable.

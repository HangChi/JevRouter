# Feature Specification: Web Trace Dashboard

**Feature Branch**: `010-web-dashboard`
**Status**: Complete

## Goal

Give an operator a browser view of what the agent did: submit a goal, watch a run progress, answer the prompts it raises, and read every step's routing probabilities, policy decision, execution result and latency. The dashboard adds no agent behaviour and changes no contract in `jev_router` or `apps/api`; it only consumes the HTTP boundary phase 9 already exposes.

## User Stories

### US1 - See what the router decided

As an operator, I need each step to show the routing signals Jev returned, the threshold each was measured against, and the control outcome the Policy Engine chose, so I can tell why a step executed, escalated, or stopped.

Acceptance scenarios:

1. Each step shows `route_confidence`, `requires_confirmation` and `needs_reasoning` as 0–1 meters with the documented threshold marked.
2. `route_risk` and `quality_score` are shown as raw numbers next to their thresholds, never as 0–1 meters, because the provider's score field is not normalized by the core package.
3. Each step shows the policy outcome and its reason verbatim.
4. A step that did not execute says so, and a denied confirmation says it was denied.
5. Each step shows its duration in milliseconds.

### US2 - Follow a run as a whole

As an operator, I need a task-level view of status, step count, diagnostic and the ordered chain of steps, so I can see where a run stopped.

Acceptance scenarios:

1. The header shows the live status (`running`, `awaiting_confirmation`, `awaiting_input`) or the terminal `RunStatus`, the step count, and the diagnostic when there is one.
2. The step chain renders in step order with each step's action and outcome.
3. The view refreshes while the run is live and stops refreshing once the run is terminal.

### US3 - Unblock a run

As an operator, I need to approve or deny a pending action and answer a pending question without leaving the task page.

Acceptance scenarios:

1. A pending confirmation shows the action and its resolved arguments, with approve and deny buttons.
2. A pending input shows the question and a text field.
3. Answering refreshes the view; a `409` because the run moved on is reported, not swallowed.

### US4 - Start a run

As an operator, I need to submit a goal from the browser and land on the new task's page.

Acceptance scenarios:

1. The home page carries a goal field and an optional context field.
2. A successful submit navigates to the new task.
3. A goal the API rejects (`422`) shows the API's message instead of a generic failure.

### US5 - Trust the boundary

As an operator, I need the dashboard to hold no credential and to fail honestly when the API is unreachable.

Acceptance scenarios:

1. No provider credential is configured in, or sent from, the web app; the browser only ever talks to the Next.js server.
2. When the API cannot be reached, the page says so and names the configured upstream instead of rendering an empty run.
3. An unknown task id renders a not-found page rather than an error stack.

## Requirements

- **FR-001**: Provide a Next.js application under `apps/web/` that renders the task list, a task detail view, and every step trace the API returns.
- **FR-002**: Perform every API call on the server. The browser never calls `apps/api` directly, and the web app configures no credential.
- **FR-003**: Read the upstream base URL from `API_UPSTREAM_URL` with a documented default of `http://127.0.0.1:8000`.
- **FR-004**: Refresh a live task view on an interval, and stop refreshing once the run reaches a terminal status.
- **FR-005**: Answer confirmation and input prompts from the task page, and surface a `409` from a stale answer.
- **FR-006**: Draw probability meters only for values the API reports as 0–1. Render `route_risk` and `quality_score` as raw numbers against their thresholds.
- **FR-007**: Render only values present in the API response; never interpolate, invent or smooth a missing field.
- **FR-008**: Leave `jev_router/` and `apps/api/` unchanged.
- **FR-009**: Keep the view-model layer pure and unit-test it offline; `tsc --noEmit`, `next build` and the vitest suite are part of the phase checks.
- **FR-010**: Mirror `apps/api/schemas.py` in TypeScript and document the mirror as a copy that must be updated when the API changes.

## Success Criteria

- A run submitted through the dashboard appears in the list and shows each step's probabilities, policy outcome, result and duration.
- A pending confirmation can be approved or denied from the task page, and the run continues or stops accordingly.
- `next build`, `tsc --noEmit`, the vitest suite and the existing Python checks all pass, with no change under `jev_router/` or `apps/api/`.

## Non-Goals

- Authentication, authorization, multi-user access and rate limiting.
- Streaming, server-sent events or WebSockets. The API exposes none, so the view polls.
- Changing `apps/api`, including an endpoint that lists persisted runs after a restart. The run registry is in-memory by phase 9's design, so a dashboard pointed at a restarted API shows no tasks; closing that gap belongs to a later phase.
- The eval runner and the comparison dashboard.
- A component library or design system; the dashboard uses Tailwind utilities and a small set of local components.
- Persisting anything in the browser beyond the current view.

# Implementation Plan: Web Trace Dashboard

## Summary

Add `apps/web/`: a Next.js application that reads the six `apps/api` endpoints from the server, renders the task list and a per-step trace view, and answers the confirmation and input prompts a run raises. No Python changes.

## Technical Context

- API: `apps/api` from phase 9, six endpoints, strict response models, `404`/`409`/`422`/`400` error mapping.
- Core: `jev_router` untouched. The dashboard is a consumer of HTTP responses only.
- Runtime: Node with npm; Next.js App Router, React, TypeScript, Tailwind.
- Tests: vitest for the pure view model and the API client with a stubbed fetch; `tsc --noEmit` and `next build` as static checks.

## Design

### Server-only API access

The browser never calls `apps/api`. `src/lib/api.ts` runs on the server — in server components for reads and in server actions for writes — and reaches the API at `API_UPSTREAM_URL`. Two consequences:

- No CORS configuration is needed in `apps/api`, and none is added.
- No credential can reach the browser, because the only credential in the system is read by the Python process from its own environment.

This is why the phase changes no Python file: a browser-to-API design would have forced a CORS change in phase 9's app factory.

### Reads are server components; the page still updates

A run is live, so a purely server-rendered page would go stale. A small client island (`<LiveRefresh intervalMs>`) calls `router.refresh()` on an interval; the server components re-run and re-render with fresh data. The island stops itself when the task is terminal, so a finished run costs no further requests. Polling rather than streaming because the API has no streaming endpoint, and adding one is out of scope.

### Writes are server actions

`submitTask`, `confirmTask` and `provideInput` are server actions that call the API and then `revalidatePath` the affected route. A `409` means the run moved on between the render and the click, so the action returns the API's message and the page renders it as a notice rather than pretending the answer landed.

### View model separated from rendering

Everything that turns a `TraceView` into something displayable is a pure function in `src/lib/viewModel.ts`. The components lay out and style; they do not decide what a status means, which branch a step took, or whether a threshold was crossed. That is what makes the interesting logic testable without a DOM.

### Honest rendering of probabilities and scores

Three of the four routing signals are `noul` probabilities in `[0, 1]` and are drawn as meters with a threshold mark. `route_risk` is a provider score over five levels and `quality_score` over four, so they are drawn as numbers plus a level strip with the raw value always visible. A missing field renders as "—", never as zero: a `NULL` column and a real `0.0` mean different things.

### Layout

Two columns on wide viewports: the task list on the left, the selected task on the right. On narrow viewports the list collapses above the detail. The step chain runs across the top of the detail view as a compact ordered strip, with one card per step below it. Colour is semantic only — outcome tones and threshold crossings — and numbers are set in a monospace face so columns of figures line up.

## Files

```text
apps/web/
├── package.json, tsconfig.json, next.config.ts, vitest.config.ts, postcss.config.mjs
├── .env.example, README.md
└── src/
    ├── app/
    │   ├── layout.tsx, globals.css, page.tsx, not-found.tsx
    │   └── tasks/[taskId]/page.tsx
    ├── lib/
    │   ├── types.ts, thresholds.ts, api.ts, viewModel.ts
    │   └── *.test.ts
    ├── components/
    │   ├── LiveRefresh.tsx, StatusBadge.tsx, TaskList.tsx, SubmitForm.tsx
    │   ├── PendingPrompt.tsx, DecisionChain.tsx, StepCard.tsx
    │   ├── ProbabilityMeter.tsx, ScoreReadout.tsx, JsonBlock.tsx
    │   └── ApiNotice.tsx
    └── actions/tasks.ts
```

## Non-Goals

Same as the specification: no auth, no streaming, no `apps/api` change, no eval work.

## Validation Strategy

1. `npx tsc --noEmit` — the mirrored types compile.
2. `npm run test` — vitest over the view model and the stubbed API client.
3. `npm run build` — the production build, which also type-checks and statically renders both routes.
4. Boot `apps/api` under uvicorn against a temporary database with a stubbed Jev client, submit a task through the dashboard, approve a pending confirmation, and read the rendered pages with curl.
5. `uv run ruff check .`, `uv run mypy jev_router apps`, `uv run pytest` — unchanged, and expected to stay green.

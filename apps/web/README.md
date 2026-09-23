# JevRouter trace dashboard

A Next.js reader for the JevRouter API (`apps/api`). It lists runs, shows every
step's routing signals, policy outcome, execution result and latency, and lets an
operator answer the confirmation and input prompts a run raises.

## Running it

Needs Node 20.9 or newer (`engines` in `package.json`; Next.js 16 does not
support older lines). The dashboard is a client of the API, so start the API
first:

```sh
# from the repository root
export JEV_API_KEY="your-key"
export JEV_MODEL="jev-latest"
uv run uvicorn apps.api.app:create_app --factory --reload
```

```sh
cd apps/web
npm install
npm run dev
```

Open <http://localhost:3000>.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `API_UPSTREAM_URL` | `http://127.0.0.1:8000` | Base URL of the `apps/api` server |

Copy `.env.example` to `.env` to change it. No other configuration exists here,
and no credential is configured or sent: every API call happens on the server,
so the browser only ever talks to this app and the provider key stays in the API
process.

## Layout

```text
src/
├── app/                     # routes: the run list and one task detail page
├── actions/tasks.ts         # server actions: submit, confirm, provide input
├── components/              # presentation only
└── lib/                     # types, thresholds, API client, view model (+ tests)
```

`src/lib/viewModel.ts` holds the pure decisions — what a status means, which
branch a step took, whether a threshold was crossed — so they are unit-tested
without rendering anything. Components lay out and style.

## Checks

```sh
npx tsc --noEmit   # types
npm run test       # vitest over the view model and the API client
npm run lint       # eslint
npm run build      # production build
```

## Known limits

- The API's run registry is in memory, so a restarted API leaves this list empty
  even though its traces are still in SQLite.
- There is no streaming, so a live run is polled every two seconds and polling
  stops when it reaches a terminal status.
- `route_risk` and `quality_score` are provider scores the core package does not
  normalize; they are shown as raw numbers with their scale stated, never as 0–1
  probability bars.

# Quickstart: Comparison Dashboard

## Run the checks

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest

cd apps/web
npx tsc --noEmit
npm run test
npm run lint
npm run build
```

## Record a run and read it back

Start the API (its database holds the runs):

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...
uv run uvicorn apps.api.app:create_app --factory
```

Run the eval and post the report:

```sh
uv run python -m evals --mode compare --api http://127.0.0.1:8000
```

Then read it:

```sh
curl -s localhost:8000/evals
curl -s localhost:8000/evals/<run_id> | python3 -m json.tool
```

`--json-out PATH` writes the same report locally instead of, or as well as, posting it.

## Read it in the dashboard

```sh
cd apps/web
API_UPSTREAM_URL=http://127.0.0.1:8000 npm run build && npm run start
```

- <http://localhost:3000/evals> — the recorded runs and the newest run's aggregate cards.
- <http://localhost:3000/evals/<run_id>> — one row per case with both routers' actions, latencies, tokens and agreement.

## Error paths worth knowing

| Situation | Answer |
| --- | --- |
| `GET /evals/<unknown>` | `404 {"detail": "eval run not found"}` |
| `GET /evals?limit=0` | `400 {"detail": "limit must be positive"}` |
| `POST /evals` with an unknown mode, unpaired compare rows, or an unknown field | `422` |
| `--api` unreachable or refusing | exit code `3`, the API's message on stderr |

## What the pages deliberately do not do

- No polling: an eval run is a finished record, unlike a live task.
- No zero for a metric a mode cannot produce: the LLM baseline has no policy outcome, so its escalation and confirmation cards are absent, and the row-level agreement cell is blank when a router errored.
- No recomputation: the API stores the rates the report carried, so the dashboard and the CLI summary always agree.

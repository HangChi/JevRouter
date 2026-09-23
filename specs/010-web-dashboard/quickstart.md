# Quickstart: Web Trace Dashboard

The dashboard is a reader of the API from phase 9. Start the API first, then the web app.

```sh
# Terminal 1 — the API (needs a real credential for live runs)
export JEV_API_KEY="your-key"
export JEV_MODEL="jev-latest"
export JEV_DATABASE_PATH="./traces.db"
uv run uvicorn apps.api.app:create_app --factory --reload
```

```sh
# Terminal 2 — the dashboard
cd apps/web
npm install
npm run dev
```

Open <http://localhost:3000>. The dashboard reads the API from `API_UPSTREAM_URL`, which defaults to `http://127.0.0.1:8000`:

```sh
# apps/web/.env
API_UPSTREAM_URL=http://127.0.0.1:8000
```

Submit a goal from the home page and follow the link to its task page. A `write` or `external` risk action pauses the run; the task page shows the action and its resolved arguments and waits for approve or deny.

The provider credential stays in the API process. The browser only ever talks to the Next.js server, which is the only component that knows `API_UPSTREAM_URL`.

## Checks

```sh
cd apps/web
npx tsc --noEmit
npm run test
npm run build
```

The Python checks are unchanged and stay green because this phase touches no Python file:

```sh
uv run ruff check .
uv run mypy jev_router apps
uv run pytest
```

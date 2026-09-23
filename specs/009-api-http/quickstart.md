# Quickstart: API HTTP Boundary

```sh
export JEV_API_KEY="your-key"
export JEV_MODEL="jev-latest"
export JEV_DATABASE_PATH="./traces.db"
export JEV_WORKSPACE_ROOT="./workspace"

uv run uvicorn apps.api.app:create_app --factory --reload
```

Interactive docs are served at `http://127.0.0.1:8000/docs`.

```sh
# Start a run; the response is immediate, the run continues in the background.
TASK=$(curl -s -X POST localhost:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"goal": "Calculate 2 + 2"}' | jq -r .task_id)

# Poll until it leaves the live states.
curl -s localhost:8000/tasks/$TASK | jq

# Read the traces as they accumulate.
curl -s localhost:8000/tasks/$TASK/traces | jq
```

A `write` or `external` risk action pauses the run:

```sh
curl -s localhost:8000/tasks/$TASK | jq '.status, .pending_confirmation'
# "awaiting_confirmation"
# { "action": "write_file", "arguments": { "path": "note.txt", "content": "hello" }, "step": 0 }

curl -s -X POST localhost:8000/tasks/$TASK/confirm \
  -H 'content-type: application/json' -d '{"approved": true}'
```

The credential is read from the environment by the server process only. It is never part of a request, a response, or a stored trace.

Run offline checks with `uv run pytest tests/test_api.py` and the full project checks.

# Quickstart: Eval Runner and LLM Baseline

## Run the checks

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

## Run an eval against the real providers

Credentials come from the environment (`.env` is not loaded by the CLI):

```sh
export JEV_API_KEY=...      # required for jev and compare
export JEV_MODEL=...        # required for jev and compare
export LLM_API_KEY=...      # required for llm and compare
export LLM_MODEL=...        # required for llm and compare

uv run python -m evals --mode compare --json-out /tmp/report.json
```

Exit codes: `0` clean, `1` at least one case errored, `2` configuration or case-file problem. Missing credentials fail before any case runs.

Other flags: `--cases PATH` (another versioned case file), `--limit N` (first N cases in file order), `--jev-model` / `--llm-model` (override the environment).

The report is `{"version": 1, "data": {...}}`; `data` is what phase 12's `POST /evals` accepts.

## Run the eval offline (no credentials)

The library takes routers, so a run needs no provider:

```python
import asyncio
from evals.cases import load_cases
from evals.registry import default_registry
from evals.runner import EvalRunner
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.router import Router

cases = load_cases()[:3]
report = asyncio.run(
    EvalRunner(
        cases=cases,
        tools=default_registry("/tmp/jevrouter-eval"),
        jev_router=Router(JevClient(JevClientConfig(api_key="x")), "model", default_registry("/tmp/jevrouter-eval")),
    ).run("jev")
)
print(report.metrics.jev.expected_match_rate)
```

`tests/test_eval_runner.py` drives exactly this shape with `httpx.MockTransport`.

## Try the LLM adapter

```python
import asyncio
from jev_router.clients.llm import LLMClient, LLMClientConfig

client = LLMClient(LLMClientConfig.from_env())
completion = asyncio.run(
    client.complete(model="claude-sonnet-4-5", system="Be terse.", prompt="2 + 2?")
)
print(completion.text, completion.input_tokens, completion.output_tokens)
```

## Enable delegation in the API

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...     # optional; both or neither
uv run uvicorn apps.api.app:create_app --factory
```

With the LLM pair set, a route that the Policy Engine sends to `delegate_to_llm` is answered by the model and recorded as that step's result. Without it the run stops with `failed` and the diagnostic `delegation was requested but no handler is configured` — the phase-7 behaviour.

## Verify against the real app

Boot the API with stubbed providers (a throwaway script under `/tmp`, not in the repo), then:

```sh
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 2 + 2"}'
curl -s localhost:8000/tasks/<task_id>
curl -s localhost:8000/tasks/<task_id>/traces
```

Queue one route above the reasoning threshold and one below it; the first step reports `policy_outcome: delegate_to_llm` with the model's text as its result, and the second executes.

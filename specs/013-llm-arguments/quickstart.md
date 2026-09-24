# Quickstart: LLM Argument Synthesis

## Run the checks

```sh
uv run ruff check .
uv run mypy jev_router apps evals
uv run pytest
```

## Configure it

The resolver and the delegate share one configuration:

```sh
export JEV_API_KEY=... JEV_MODEL=...
export LLM_API_KEY=... LLM_MODEL=...     # optional; both or neither
```

Without the LLM pair nothing changes: the resolver is absent, a tool call
resolves to `{}` and the tool's own schema refuses it, and the run stops with
`tool 'X' rejected its input`.

`LLM_MAX_TOKENS` (default 1024) bounds what the model can generate, so it bounds
synthesized file content. A run that needs to write something very large needs a
higher value — the tool's own limit is 1,000,000 bytes.

## Watch it work

Submit a goal that needs a tool:

```sh
uv run uvicorn apps.api.app:create_app --factory
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 6 * 7"}'
curl -s localhost:8000/tasks/<task_id>/traces | python3 -m json.tool
```

The trace's step shows `arguments` as the model produced them, the tool's real
output in `result`, and `executed: true`.

## Adding a tool

Declare the model `execute` validates against, and describe the fields:

```python
class MyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, description="What to act on.")


class MyTool:
    name = "my_tool"
    description = "Does the thing."
    risk: RiskLevel = "read"
    input_model: type[BaseModel] = MyInput

    def execute(self, input: dict[str, Any]) -> ToolResult:
        request = MyInput.model_validate(input)
        ...
```

The description is what the model reads, so state the constraint the code
enforces (a relative path, a whitelist, a size limit) rather than restating the
type. A test asserts every registered tool declares a model whose fields its
`execute` accepts.

## Verify against the real app

Boot with stubbed providers (a throwaway script under `/tmp`): stub the Jev
client to route once to `calculator` and verify once, stub the LLM client to
return `{"expression": "6 * 7"}`, and pass `llm_client=<stub>` to `create_app`
with `resolver` left unset. Then:

```sh
curl -s localhost:8000/tasks -H 'content-type: application/json' \
  -d '{"goal": "Calculate 6 * 7"}'
curl -s localhost:8000/tasks/<task_id>/traces
```

Expect `completed`, `arguments == {"expression": "6 * 7"}` and
`result == {"result": 42.0}`.

## Failure paths

| Situation | Outcome |
| --- | --- |
| Provider error during synthesis | failed run, diagnostic `argument synthesis failed: <category>` |
| Completion is not a JSON object, is empty, or names no accepted field | failed run, diagnostic naming the parse problem |
| Model returns arguments the tool refuses | failed run, the tool's own message; the attempted arguments stay in the trace |
| No LLM configured | unchanged phase-7 behaviour |

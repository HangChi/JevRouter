# Data Model: LLM Argument Synthesis

## `Tool.input_model` (`jev_router/tools/base.py`)

```python
class Tool(Protocol):
    name: str
    description: str
    risk: RiskLevel
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
```

The pydantic model the tool's `execute` already validates against. It is the
single source of truth for two consumers: the tool's own validation, and the
prompt the argument resolver builds. Nothing else describes a tool's input, so
the two cannot drift — the dangerous direction, because a drifted prompt would
advertise a field the tool refuses and look like a working call.

The declared type is widened to `type[BaseModel]` on each tool
(`input_model: type[BaseModel] = CalculatorInput`) because protocol members are
invariant: `type[CalculatorInput]` is not assignable to `type[BaseModel]`.

| Tool | Model | Notes |
| --- | --- | --- |
| `calculator` | `CalculatorInput` | `expression`, max 256 |
| `knowledge_search` | `SearchInput` | `query`, optional `limit` |
| `web_search` | `SearchInput` | shared with knowledge search |
| `write_file` | `WriteFileInput` | `path`, `content` |
| `send_mock_email` | `MockEmailInput` | `to`, `subject`, `body` |

Each field now carries `Field(description=...)`. The generated schema previously
said only `{"expression": {"type": "string", "maxLength": 256}}` — enough to
guess a name, not enough to produce a *correct* value. `write_file`'s path rule
(relative, inside the workspace root, no overwrite) lives in the tool's body, so
without prose the model would emit absolute paths and every write would fail.

## The resolver (`apps/api/llm.py`)

```text
LLMArgumentResolver(client: Completer, model: str, tools: ToolRegistry)
    async def resolve(action: str, state: TaskState) -> dict[str, Any]
```

Prompt sections, in order: the state block (goal, step, context, clipped
history, last result), the action, the tool's description and risk, the rendered
schema, and the response contract.

The schema renderer emits one line per field:

```text
- path (string, required) [min length 1; max length 512]: A relative path inside the workspace root; absolute paths and '..' are refused, and an existing file is not overwritten.
- limit (integer, optional, defaults to 5) [min 1; max 20]: How many results to return at most.
```

Only what changes whether the tool accepts the value is rendered — titles and
`additionalProperties` are dropped.

Parsing: the whole completion is tried as JSON, then the first brace-balanced
object is extracted (so a fenced answer works). The result must be a non-empty
object sharing at least one key with the tool's fields. Anything else raises
`ValueError`, which escapes `Runner.run()` and becomes a failed run through
`TaskService._drive`'s existing catch-all.

The resolver returns the model's object unchanged. Unknown keys are *not*
filtered: `extra="forbid"` on every input model means the tool refuses them, and
filtering here would make the resolver a second, weaker authority.

## Assembly (`apps/api/service.py`)

```python
self._delegate, llm_resolver = self._build_llm_collaborators(llm_client)
self._resolver = resolver if resolver is not None else llm_resolver
```

One settings pair (`llm`, `llm_model`) drives both collaborators. An explicitly
injected `resolver` wins over the LLM one, because injection is the caller's own
seam — the test suite relies on it.

## No new persisted state

Nothing about this phase reaches the database. The arguments the resolver
produced already land in `StepTrace.arguments` and therefore in `agent_steps`,
because the Runner records them exactly as it records an injected resolver's.

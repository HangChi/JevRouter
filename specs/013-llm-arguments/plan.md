# Implementation Plan: LLM Argument Synthesis

## Design Decisions

### 1. The Tool protocol gains the model it already validates against

```python
class Tool(Protocol):
    name: str
    description: str
    risk: RiskLevel
    input_model: type[BaseModel]

    def execute(self, input: dict[str, Any]) -> ToolResult: ...
```

A tool that cannot describe its input cannot be driven by a model, and the only
honest description is the one validation already uses. Deriving the prompt from
`input_model.model_json_schema()` makes it impossible for the prompt to advertise
a field the tool would refuse — the drift this avoids is the dangerous kind,
because it would look like a working call.

The five tools each declare the model they already import. Three test stubs gain
a one-line model. `web_search` and `knowledge_search` share `SearchInput`, which
already lives in `knowledge_search.py`.

### 2. Field descriptions, not bare types

The generated schemas say `{"expression": {"type": "string", "maxLength": 256}}`
— enough to guess a name, not enough to produce a *correct* value. `write_file`'s
path must be relative to the workspace root; that rule lives in the tool's body,
so without prose in the schema the model would emit absolute paths and every
write would fail. Adding `Field(description=...)` to the four input models puts
the constraint next to the code that enforces it, and the schema renderer picks
it up for free.

### 3. One module for the LLM-backed collaborators

`apps/api/llm.py` holds both `LLMArgumentResolver` and the `LLMDelegate` phase 11
left in `service.py`. They are the same shape — one injected client, one model,
one prompt builder, one error taxonomy — and keeping them apart would duplicate
the failure handling. `service.py` keeps owning assembly and the run registry.

### 4. Failure is loud, and lands where the Runner already puts it

The resolver raises `ValueError` carrying the provider category or the parse
problem. `Runner.run()` lets it escape (only `_Stop` and `JevClientError` are
handled inside), and `TaskService._drive`'s existing catch-all turns it into a
failed run with the message in the diagnostic. That is the same path phase 11's
delegate uses, and it is deliberate: a synthesis that silently produced `{}`
would execute a tool with no arguments, which is worse than a stopped run.

The resolver returns the model's object unchanged — no filtering, no defaults.
The tool's pydantic model is the authority, so a violating argument fails exactly
as a hand-written one would.

### 5. Prompt shape

```text
Goal: ...
Step: N
Context: {...}
Completed steps:
- step 1: web_search -> {...}
Last result: {...}

Action to perform: write_file
Description: Write a bounded text file under a configured root directory.
Risk: write

Arguments (respond with one JSON object using exactly these keys):
- path (string, required): A relative path inside the workspace root; ...
- content (string, required): The full text to write; ...

Respond with exactly one JSON object and nothing else.
```

The schema renderer emits one line per field with type, required/optional,
constraints that affect validity (min/max length, min/max value, default) and the
description. Titles and `additionalProperties` are dropped as noise.

## File Layout

```text
jev_router/tools/base.py                 + input_model on the protocol
jev_router/tools/{calculator,write_file,mock_email,knowledge_search}.py
                                        + input_model, + field descriptions
apps/api/llm.py                          new: LLMArgumentResolver, LLMDelegate
apps/api/service.py                      assemble both, import from llm.py
tests/test_api_llm.py                    new: prompt, parse, failures, settings
tests/test_router.py, test_policy.py,
  tests/test_runner.py                   stub tools gain input_model
tests/test_api.py                        end-to-end run with a real tool
```

## Testing Strategy

- Resolver unit tests with a stub completer: the prompt carries every required
  element; bare and fenced JSON parse; a non-object, a missing key and an
  unknown key each raise; a provider error carries its category.
- Schema renderer tests: required/optional, defaults, length and range
  constraints, and a description reaching the line.
- API tests: a run that routes to `calculator` and executes with synthesized
  arguments (traces show the model's arguments and the tool's real output); a
  synthesis failure producing a failed run with a diagnostic; an unconfigured
  service behaving exactly as before.
- Tool tests: the five tools still validate identically, and each declares the
  model its `execute` validates against.

## Risks

- **Protocol churn**: adding a required member touches every tool and stub.
  Bounded and mechanical; a test asserts every registered tool declares a model
  whose fields the tool actually accepts.
- **Prompt size**: history is clipped as the delegate's is, so a long run cannot
  grow the prompt without bound.
- **Model output quality**: the model may produce arguments the tool rejects.
  That is the designed failure — the run stops with the tool's own message, and
  the trace shows what was attempted.

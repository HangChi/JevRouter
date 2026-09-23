# Quickstart: Tool Registry

## Construct tools

```python
from pathlib import Path

from jev_router.tools import (
    CalculatorTool,
    KnowledgeSearchTool,
    MockEmailTool,
    SearchDocument,
    ToolRegistry,
    WebSearchMockTool,
    WriteFileTool,
)

registry = ToolRegistry([
    CalculatorTool(),
    KnowledgeSearchTool([SearchDocument(title="Guide", content="Local reference text")]),
    WebSearchMockTool(),
    WriteFileTool(Path("./workspace")),
    MockEmailTool(),
])
```

The application constructs the allowlist. Do not derive registrations or permissions from model output.

## Execute and validate offline

```python
answer = registry.execute("calculator", {"expression": "(2 + 3) * 4"})
assert answer.output["result"] == 20.0
```

All tools expose synchronous `execute(input)` and return a `ToolResult`. Search requires injected local data/fixtures. `write_file` is constrained to its configured root and refuses existing files unless `allow_overwrite=True` is explicitly configured. `send_mock_email` only returns a local simulation.

Run the checks from the repository root:

```sh
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

No live credentials or network connection are needed.

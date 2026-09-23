# Quickstart: Decision Router

```python
from jev_router import Router
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.tools import CalculatorTool, ToolRegistry

client = JevClient(JevClientConfig.from_env())
registry = ToolRegistry([CalculatorTool()])
router = Router(client, model="jev-latest", tools=registry)
decision = await router.route({"goal": "Calculate 2 + 2", "current_step": 0})

print(decision.action, decision.confidence, decision.risk)
```

The result is a recommendation only. Application policy must independently decide whether a selected action is permitted and whether confirmation is needed. The Router never executes tools.

Run offline checks from the repository root:

```sh
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

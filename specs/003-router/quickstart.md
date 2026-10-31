# 快速开始：决策路由层

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

该结果只是一条建议。应用策略必须独立判定所选动作是否被允许、是否需要确认。路由层（Router）从不执行工具。

在仓库根目录运行离线检查：

```sh
uv run ruff check .
uv run mypy jev_router
uv run pytest
```

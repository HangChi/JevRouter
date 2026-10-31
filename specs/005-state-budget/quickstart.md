# 快速开始：任务状态与预算

```python
from jev_router import ExecutionBudget, TaskState

state = TaskState(goal="Calculate 2 + 2", context={"source": "user"})
budget = ExecutionBudget(max_steps=4, max_model_calls=3)

budget = budget.consume_model_call()
state = state.advance(action="calculator", result={"value": 4})
budget = budget.consume_step()
```

每个操作都会返回一个新的不可变快照。已耗尽的计数器会抛出 `ValueError`。本阶段不运行循环，也不调用工具或模型。

在仓库根目录通过 `uv run pytest tests/test_state.py` 运行离线检查，并运行完整的项目检查。

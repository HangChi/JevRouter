# 快速开始：策略引擎

```python
from jev_router import PolicyEngine, Router

router = Router(client, model="jev-latest", tools=registry)
route = await router.route(task_state)
policy = PolicyEngine(registry)
decision = policy.evaluate(route)

if decision.outcome == "execute":
    await request_authorized_execution(decision.action)
elif decision.outcome == "ask_confirmation":
    await request_explicit_user_confirmation(decision.action)
```

策略结果不会执行工具。执行由调用方负责；`ask_confirmation` 结果要求在任何副作用之前单独获得一次显式批准。

初始阈值是 `doc.md` 中描述的 MVP 取值，而非厂商建议。运行 `uv run pytest tests/test_policy.py` 执行离线策略测试。

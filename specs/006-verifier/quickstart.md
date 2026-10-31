# 快速开始：Jev 验证器

```python
from jev_router import TaskState, Verifier
from jev_router.clients.jev import JevClient, JevClientConfig

state = TaskState(goal="Calculate 2 + 2").advance(
    action="calculator", result={"value": 4}
)
verifier = Verifier(JevClient(JevClientConfig.from_env()), model="jev-latest")
assessment = await verifier.verify(state)
print(assessment.completion_probability, assessment.quality_score)
```

验证只是一次评估。由调用方或后续的执行循环（Runner）决定是结束还是再次路由。

通过 `uv run pytest tests/test_verifier.py` 运行离线检查，并运行完整的项目检查。

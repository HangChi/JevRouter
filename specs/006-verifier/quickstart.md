# Quickstart: Jev Verifier

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

Verification is an assessment only. The caller or a later Runner decides whether to finish or route again.

Run offline checks with `uv run pytest tests/test_verifier.py` and the full project checks.

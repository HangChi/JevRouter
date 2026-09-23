# Quickstart: Task State and Budget

```python
from jev_router import ExecutionBudget, TaskState

state = TaskState(goal="Calculate 2 + 2", context={"source": "user"})
budget = ExecutionBudget(max_steps=4, max_model_calls=3)

budget = budget.consume_model_call()
state = state.advance(action="calculator", result={"value": 4})
budget = budget.consume_step()
```

Each operation returns a new immutable snapshot. Exhausted counters raise `ValueError`. This phase does not run a loop or invoke tools or models.

Run offline checks from the repository root with `uv run pytest tests/test_state.py` and the full project checks.

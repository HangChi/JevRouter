# Quickstart: Policy Engine

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

The policy outcome does not execute the tool. The caller owns execution, and an `ask_confirmation` result requires a separate explicit approval before any side effect.

Initial thresholds are MVP values described in `doc.md`, not vendor recommendations. Run `uv run pytest tests/test_policy.py` for offline policy tests.

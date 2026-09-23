# Quickstart: Bounded Runner

```python
import asyncio
import json

import httpx

from jev_router import Runner
from jev_router.clients.jev import JevClient, JevClientConfig
from jev_router.router import RISK_LEVELS
from jev_router.state import ExecutionBudget
from jev_router.tools import CalculatorTool, ToolRegistry
from jev_router.verifier import QUALITY_LEVELS

CANDIDATES = ("calculator", "ask_user", "delegate_to_llm", "finish")


class Arguments:
    """Stand-in for the LLM-backed resolver that a later phase will supply."""

    async def resolve(self, action, state):
        return {"expression": "2 + 2"}


class FakeJev:
    """Answers the route question set once, then the verification set once."""

    def transport(self):
        async def handler(request):
            questions = json.loads(request.content)["questions"]
            if "next_action" in questions:
                answers = {
                    "next_action": {
                        "type": "choice",
                        "choice": "calculator",
                        "probabilities": {name: 1.0 if name == "calculator" else 0.0
                                          for name in CANDIDATES},
                        "confidence": 0.9,
                    },
                    "risk": {
                        "type": "score",
                        "score": 1.0,
                        "legend": list(RISK_LEVELS),
                        "probabilities": {level: 0.2 for level in RISK_LEVELS},
                        "confidence": 0.8,
                    },
                    "requires_confirmation": {"type": "noul", "noul": 0.1},
                    "needs_reasoning": {"type": "noul", "noul": 0.1},
                }
            else:
                answers = {
                    "task_complete": {"type": "noul", "noul": 0.82},
                    "result_quality": {
                        "type": "score",
                        "score": 3.0,
                        "legend": list(QUALITY_LEVELS),
                        "probabilities": {level: 0.25 for level in QUALITY_LEVELS},
                        "confidence": 0.6,
                    },
                }
            return httpx.Response(
                200,
                json={
                    "model": "jev-latest",
                    "answers": answers,
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )

        return httpx.MockTransport(handler)


async def main():
    runner = Runner(
        client=JevClient(JevClientConfig(api_key="local-key"), FakeJev().transport()),
        model="jev-latest",
        tools=ToolRegistry([CalculatorTool()]),
        budget=ExecutionBudget(max_steps=4, max_model_calls=8),
        resolver=Arguments(),
    )
    result = await runner.run("Calculate 2 + 2")

    print(result.status)              # completed
    print(result.state.last_result)   # {'result': 4.0}
    for trace in result.traces:
        print(trace.step, trace.action, trace.policy_outcome, trace.executed)


asyncio.run(main())
```

A `write` or `external` risk tool additionally requires a `ConfirmationHandler`; without one the run stops at `needs_confirmation` before any side effect. The handler receives the resolved arguments, so it can show the user exactly what will run.

Run offline checks with `uv run pytest tests/test_runner.py` and the full project checks.

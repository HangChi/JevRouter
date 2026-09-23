# Quickstart: Trace Persistence

```python
import asyncio
import json

import httpx

from apps.api.storage import TraceStore
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
    with TraceStore("traces.db") as store:
        runner = Runner(
            client=JevClient(JevClientConfig(api_key="local-key"), FakeJev().transport()),
            model="jev-latest",
            tools=ToolRegistry([CalculatorTool()]),
            budget=ExecutionBudget(max_steps=4, max_model_calls=8),
            resolver=Arguments(),
            # Each step is written as the Runner emits it, so a run that is
            # killed mid-flight still leaves a readable trace.
            trace_sink=store.sink(),
        )
        result = await runner.run("Calculate 2 + 2")

        # Replaces the "running" marker with the terminal status.
        store.record(result)

        task = store.load_task(result.task_id)
        print(task.status, task.step)          # completed 1

        for trace in store.load_traces(result.task_id):
            print(trace.step, trace.action, trace.policy_outcome, trace.executed)


asyncio.run(main())
```

Pass `redact=` to scrub results, arguments and state snapshots before they are encoded. The store never sees `JevClientConfig`, so a credential cannot reach the database through it.

Run offline checks with `uv run pytest tests/test_storage.py` and the full project checks.

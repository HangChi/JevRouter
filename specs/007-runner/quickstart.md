# 快速开始：有界执行循环（Runner）

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

`write` 或 `external` 风险工具额外需要一个 `ConfirmationHandler`；若没有，运行会在任何副作用发生之前停在 `needs_confirmation`。该处理器接收解析后的参数，因此可以准确告知用户将要运行什么。

通过 `uv run pytest tests/test_runner.py` 运行离线检查，并运行完整的项目检查。

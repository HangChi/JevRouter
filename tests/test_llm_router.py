from __future__ import annotations

from typing import Any

import pytest

from evals.llm_router import LLMRouter, LLMRouterError
from jev_router.clients.llm import LLMCompletion
from jev_router.tools import (
    CalculatorTool,
    MockEmailTool,
    ToolRegistry,
    WebSearchMockTool,
    WriteFileTool,
)

MODEL = "claude-sonnet-4-5"


class StubCompleter:
    """用预置文本回答每次补全，并记录下提示词。"""

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []
        self.systems: list[str] = []

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> LLMCompletion:
        self.prompts.append(prompt)
        self.systems.append(system)
        return LLMCompletion(
            text=self.text,
            model=MODEL,
            input_tokens=310,
            output_tokens=14,
        )


def registry(tmp_path: Any) -> ToolRegistry:
    return ToolRegistry(
        [
            CalculatorTool(),
            WebSearchMockTool(),
            WriteFileTool(tmp_path),
            MockEmailTool(),
        ]
    )


def state(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "goal": "check the weather in Tokyo tomorrow",
        "step": 0,
        "context": {},
        "history": [],
        "last_result": None,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_bare_json_object_is_parsed(tmp_path: Any) -> None:
    completer = StubCompleter('{"action": "web_search", "reason": "current information"}')
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    decision = await router.route(state())
    assert decision.action == "web_search"
    assert decision.reason == "current information"
    assert decision.model == MODEL
    assert (decision.input_tokens, decision.output_tokens) == (310, 14)
    assert decision.latency_ms >= 0


@pytest.mark.asyncio
async def test_fenced_json_is_parsed(tmp_path: Any) -> None:
    completer = StubCompleter(
        'Sure.\n```json\n{"action": "calculator", "reason": "arithmetic"}\n```\nDone.'
    )
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    decision = await router.route(state(goal="what is 2**10"))
    assert decision.action == "calculator"


@pytest.mark.asyncio
async def test_prompt_carries_the_goal_history_and_every_candidate(tmp_path: Any) -> None:
    completer = StubCompleter('{"action": "finish", "reason": "done"}')
    tools = registry(tmp_path)
    router = LLMRouter(completer, MODEL, tools)
    await router.route(
        state(
            goal="find the weather then write it down",
            step=1,
            history=[{"step": 1, "action": "web_search", "result": {"results": []}}],
            last_result={"results": []},
        )
    )
    prompt = completer.prompts[0]
    assert "find the weather then write it down" in prompt
    assert "step 1: web_search" in prompt
    for name in (*tools.names(), "ask_user", "delegate_to_llm", "finish"):
        assert f"- {name}:" in prompt


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(tmp_path: Any) -> None:
    completer = StubCompleter('{"action": "drop_database", "reason": "why not"}')
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    with pytest.raises(LLMRouterError):
        await router.route(state())


@pytest.mark.asyncio
async def test_malformed_completion_is_rejected(tmp_path: Any) -> None:
    completer = StubCompleter("I think you should search the web.")
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    with pytest.raises(LLMRouterError):
        await router.route(state())


@pytest.mark.asyncio
async def test_missing_action_key_is_rejected(tmp_path: Any) -> None:
    completer = StubCompleter('{"reason": "no action here"}')
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    with pytest.raises(LLMRouterError):
        await router.route(state())


@pytest.mark.asyncio
async def test_non_string_reason_is_rejected(tmp_path: Any) -> None:
    completer = StubCompleter('{"action": "finish", "reason": 7}')
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    with pytest.raises(LLMRouterError):
        await router.route(state())


@pytest.mark.asyncio
async def test_non_dict_state_is_serialized_into_the_prompt(tmp_path: Any) -> None:
    completer = StubCompleter('{"action": "finish", "reason": "done"}')
    router = LLMRouter(completer, MODEL, registry(tmp_path))
    await router.route(["goal", "history"])
    assert "goal" in completer.prompts[0]


def test_blank_model_is_rejected(tmp_path: Any) -> None:
    with pytest.raises(ValueError):
        LLMRouter(StubCompleter("{}"), "  ", registry(tmp_path))

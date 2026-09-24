from __future__ import annotations

from typing import Any

import pytest

from apps.api.llm import (
    LLMArgumentResolver,
    LLMDelegate,
    _render_schema,
)
from jev_router.clients.llm import LLMCompletion, LLMHttpError
from jev_router.state import TaskState
from jev_router.tools import CalculatorTool, MockEmailTool, ToolRegistry, WriteFileTool

MODEL = "claude-sonnet-4-5"


class StubCompleter:
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
            text=self.text, model=MODEL, input_tokens=200, output_tokens=30
        )


class BrokenCompleter:
    async def complete(self, **kwargs: Any) -> LLMCompletion:
        raise LLMHttpError(429)


def registry(tmp_path: Any) -> ToolRegistry:
    return ToolRegistry([CalculatorTool(), WriteFileTool(tmp_path), MockEmailTool()])


def resolver(tmp_path: Any, text: str) -> tuple[LLMArgumentResolver, StubCompleter]:
    completer = StubCompleter(text)
    return LLMArgumentResolver(completer, MODEL, registry(tmp_path)), completer


def state(**overrides: Any) -> TaskState:
    values: dict[str, Any] = {"goal": "write tomorrow's Tokyo weather to weather.txt"}
    values.update(overrides)
    return TaskState(**values)


@pytest.mark.asyncio
async def test_the_prompt_carries_everything_the_model_needs(tmp_path: Any) -> None:
    subject, completer = resolver(tmp_path, '{"path": "weather.txt", "content": "rain"}')
    await subject.resolve("write_file", state())

    prompt = completer.prompts[0]
    assert "Goal: write tomorrow's Tokyo weather to weather.txt" in prompt
    assert "Step: 0" in prompt
    assert "- (none)" in prompt
    assert "Action to perform: write_file" in prompt
    assert "Description: Write a bounded text file under a configured root directory." in prompt
    assert "Risk: write" in prompt
    assert "- path (string, required) [min length 1; max length 512]:" in prompt
    assert "A relative path inside the workspace root" in prompt
    assert "- content (string, required) [max length 1000000]:" in prompt


@pytest.mark.asyncio
async def test_the_prompt_carries_history_and_the_last_result(tmp_path: Any) -> None:
    subject, completer = resolver(tmp_path, '{"expression": "2 + 2"}')
    advanced = state().advance("web_search", {"results": [{"title": "Tokyo"}]})
    await subject.resolve("calculator", advanced)

    prompt = completer.prompts[0]
    assert "Step: 1" in prompt
    assert "- step 1: web_search ->" in prompt
    assert '"last_result"' in prompt or "Tokyo" in prompt


@pytest.mark.asyncio
async def test_bare_json_is_parsed(tmp_path: Any) -> None:
    subject, _ = resolver(tmp_path, '{"expression": "2 + 2"}')
    assert await subject.resolve("calculator", state()) == {"expression": "2 + 2"}


@pytest.mark.asyncio
async def test_fenced_json_is_parsed(tmp_path: Any) -> None:
    subject, _ = resolver(
        tmp_path, 'Here you go.\n```json\n{"expression": "3 * 3"}\n```'
    )
    assert await subject.resolve("calculator", state()) == {"expression": "3 * 3"}


@pytest.mark.asyncio
async def test_a_non_object_completion_is_refused(tmp_path: Any) -> None:
    subject, _ = resolver(tmp_path, '["expression", "2 + 2"]')
    with pytest.raises(ValueError, match="JSON object"):
        await subject.resolve("calculator", state())


@pytest.mark.asyncio
async def test_an_empty_object_is_refused(tmp_path: Any) -> None:
    subject, _ = resolver(tmp_path, "{}")
    with pytest.raises(ValueError, match="JSON object"):
        await subject.resolve("calculator", state())


@pytest.mark.asyncio
async def test_an_object_with_no_known_field_is_refused(tmp_path: Any) -> None:
    subject, _ = resolver(tmp_path, '{"equation": "2 + 2"}')
    with pytest.raises(ValueError, match="no argument the tool accepts"):
        await subject.resolve("calculator", state())


@pytest.mark.asyncio
async def test_unknown_fields_are_returned_for_the_tool_to_refuse(tmp_path: Any) -> None:
    """The resolver does not filter: the tool's own schema is the authority."""
    subject, _ = resolver(tmp_path, '{"expression": "2 + 2", "surprise": 1}')
    assert await subject.resolve("calculator", state()) == {
        "expression": "2 + 2",
        "surprise": 1,
    }


@pytest.mark.asyncio
async def test_an_unregistered_action_is_refused(tmp_path: Any) -> None:
    subject, _ = resolver(tmp_path, '{"expression": "2 + 2"}')
    with pytest.raises(ValueError, match="not registered"):
        await subject.resolve("drop_database", state())


@pytest.mark.asyncio
async def test_a_provider_error_carries_its_category(tmp_path: Any) -> None:
    subject = LLMArgumentResolver(BrokenCompleter(), MODEL, registry(tmp_path))
    with pytest.raises(ValueError, match="argument synthesis failed: http"):
        await subject.resolve("calculator", state())


@pytest.mark.asyncio
async def test_a_long_history_is_clipped(tmp_path: Any) -> None:
    subject, completer = resolver(tmp_path, '{"expression": "1 + 1"}')
    advanced = state()
    for index in range(6):
        advanced = advanced.advance("web_search", {"blob": "x" * 900})
    await subject.resolve("calculator", advanced)

    prompt = completer.prompts[0]
    # The clip is per result, so each history line stays bounded no matter how
    # long the run gets; the prompt as a whole still grows with the step count.
    history_lines = [line for line in prompt.split("\n") if line.startswith("- step ")]
    assert len(history_lines) == 6
    assert all(len(line) <= 530 for line in history_lines)
    assert "..." in prompt


def test_the_schema_renderer_emits_type_required_and_constraints() -> None:
    rendered = _render_schema(CalculatorTool.input_model)
    assert rendered == (
        "- expression (string, required) [min length 1; max length 256]: "
        "One arithmetic expression using + - * / // % ** and parentheses, "
        "with numeric literals only."
    )


def test_the_schema_renderer_marks_optional_fields_with_their_default() -> None:
    from jev_router.tools.knowledge_search import SearchInput

    rendered = _render_schema(SearchInput)
    assert "- limit (integer, optional, defaults to 5) [min 1; max 20]:" in rendered


@pytest.mark.asyncio
async def test_the_delegate_returns_the_model_text() -> None:
    delegate = LLMDelegate(StubCompleter("the reasoned answer"), MODEL)
    assert await delegate.delegate(state()) == "the reasoned answer"


@pytest.mark.asyncio
async def test_the_delegate_refuses_an_empty_answer() -> None:
    delegate = LLMDelegate(StubCompleter("   "), MODEL)
    with pytest.raises(ValueError, match="no result"):
        await delegate.delegate(state())


@pytest.mark.asyncio
async def test_the_delegate_carries_a_provider_error_category() -> None:
    delegate = LLMDelegate(BrokenCompleter(), MODEL)
    with pytest.raises(ValueError, match="delegation failed: http"):
        await delegate.delegate(state())

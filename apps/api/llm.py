from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel

from jev_router.clients.llm import LLMClientError, LLMCompletion
from jev_router.state import TaskState
from jev_router.tools.registry import ToolRegistry

# 两个协作者都会把运行的 state 发给提供商，因此过长的历史会被裁剪，
# 而不是任由提示词无界增长。
_RESULT_LIMIT = 500

_DELEGATE_SYSTEM = (
    "You are the reasoning delegate of an agent. The router decided that this "
    "step needs deeper reasoning than a typed decision can provide. Produce the "
    "answer or the concrete content that advances the task, as plain text."
)

_RESOLVER_SYSTEM = (
    "You synthesize the arguments for one tool call of an agent. The tool "
    "validates what you return against its own schema, so use exactly the "
    "documented argument names and respect their constraints. Answer with one "
    "JSON object and nothing else."
)


class Completer(Protocol):
    """两个协作者所需的 ``LLMClient`` 子集，便于测试注入替身。"""

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> LLMCompletion: ...


class LLMDelegate:
    """用 LLM 生成的推理结果应答一次委托。

    Runner 会把返回的文本记为 ``delegate_to_llm`` 步骤的结果，因此下一次路由
    能在历史中看到它；这里不执行任何东西。提供商故障会变成携带错误类别的
    ``ValueError``，Runner 会让它逃出 ``run()``，服务再把它变成一次失败的运行
    —— 一次默不作声、什么都没产出的委托只会更糟。
    """

    def __init__(self, client: Completer, model: str) -> None:
        self._client = client
        self._model = model

    async def delegate(self, state: TaskState) -> str:
        try:
            completion = await self._client.complete(
                model=self._model,
                system=_DELEGATE_SYSTEM,
                prompt=_delegation_prompt(state),
            )
        except LLMClientError as exc:
            raise ValueError(f"委托失败：{exc.category}") from exc
        if not completion.text.strip():
            raise ValueError(
                "委托处理器没有返回结果；推理模型返回空补全通常意味着在任何"
                "内容产出之前 LLM_MAX_TOKENS 就被耗尽"
            )
        return completion.text


class LLMArgumentResolver:
    """根据目标和运行历史合成一次工具调用的参数。

    模型的输出是不可信输入：它原样返回，工具的 pydantic 模型仍然是权威，
    因此合成出来的参数会像手写参数一样失败。提示词里的 schema 也派生自同一个
    模型，所以提示词不可能宣告工具会拒绝的字段。

    补全内容不是 JSON 对象、为空，或没有给出工具接受的任何字段时会抛错，
    而不是退化成空参数 —— 拿空参数去执行工具比让运行停下来更糟。
    """

    def __init__(self, client: Completer, model: str, tools: ToolRegistry) -> None:
        self._client = client
        self._model = model
        self._tools = tools

    async def resolve(self, action: str, state: TaskState) -> dict[str, Any]:
        try:
            tool = self._tools.get(action)
        except KeyError as exc:
            raise ValueError(f"动作 {action!r} 未注册") from exc
        try:
            completion = await self._client.complete(
                model=self._model,
                system=_RESOLVER_SYSTEM,
                prompt=_resolver_prompt(action, tool, state),
            )
        except LLMClientError as exc:
            raise ValueError(f"参数合成失败：{exc.category}") from exc
        return _parse_arguments(completion.text, tool.input_model)


def _delegation_prompt(state: TaskState) -> str:
    return "\n".join(
        [
            _state_prompt(state),
            "",
            "Produce the content that advances this task.",
        ]
    )


def _resolver_prompt(action: str, tool: Any, state: TaskState) -> str:
    return "\n".join(
        [
            _state_prompt(state),
            "",
            f"Action to perform: {action}",
            f"Description: {tool.description}",
            f"Risk: {tool.risk}",
            "",
            "Arguments (respond with one JSON object using exactly these keys):",
            _render_schema(tool.input_model),
            "",
            "Respond with exactly one JSON object and nothing else.",
        ]
    )


def _state_prompt(state: TaskState) -> str:
    if state.history:
        rendered = []
        for record in state.history:
            result = _clip(record.result)
            rendered.append(f"- step {record.step}: {record.action} -> {result}")
        history_text = "\n".join(rendered)
    else:
        history_text = "- (none)"
    return "\n".join(
        [
            f"Goal: {state.goal}",
            f"Step: {state.step}",
            f"Context: {_clip(state.context)}",
            "Completed steps:",
            history_text,
            f"Last result: {_clip(state.last_result)}",
        ]
    )


def _render_schema(model: type[BaseModel]) -> str:
    """每个字段一行：类型、是否必填、有效性约束、描述。

    只渲染会影响工具是否接受该值的部分 —— title 和 `additionalProperties`
    只会被模型拿去做模式匹配，属于噪声。
    """
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    lines: list[str] = []
    for name, spec in schema.get("properties", {}).items():
        parts = [str(spec.get("type", "any"))]
        if name in required:
            parts.append("required")
        elif "default" in spec:
            parts.append(f"optional, defaults to {spec['default']!r}")
        else:
            parts.append("optional")
        constraints: list[str] = []
        for key, label in (
            ("minLength", "min length"),
            ("maxLength", "max length"),
            ("minimum", "min"),
            ("maximum", "max"),
        ):
            if key in spec:
                constraints.append(f"{label} {spec[key]}")
        line = f"- {name} ({', '.join(parts)})"
        if constraints:
            line += f" [{'; '.join(constraints)}]"
        description = spec.get("description")
        if isinstance(description, str) and description:
            line += f": {description}"
        lines.append(line)
    return "\n".join(lines)


def _parse_arguments(text: str, model: type[BaseModel]) -> dict[str, Any]:
    if not text.strip():
        raise ValueError(
            "补全内容为空；LLM_MAX_TOKENS 设得过小的推理模型会在产出内容"
            "之前就把预算花光"
        )
    payload = _extract_object(text)
    if not payload:
        raise ValueError("补全内容中没有参数的 JSON 对象")
    known = set(model.model_json_schema().get("properties", {}))
    if not known & set(payload):
        raise ValueError(
            f"补全内容没有给出工具接受的任何参数：{sorted(payload)}"
        )
    return dict(payload)


def _extract_object(text: str) -> dict[str, Any]:
    """从补全内容中读出 JSON 对象，无论是否带代码围栏。"""
    for candidate in (text, _first_braced_object(text)):
        if candidate is None:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("补全内容里没有一个 JSON 对象（可能是数组、裸值或带多余文字）")


def _first_braced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _clip(value: Any) -> str:
    text = json.dumps(value, default=str, sort_keys=True)
    return text if len(text) <= _RESULT_LIMIT else text[: _RESULT_LIMIT - 3] + "..."

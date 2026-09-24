from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel

from jev_router.clients.llm import LLMClientError, LLMCompletion
from jev_router.state import TaskState
from jev_router.tools.registry import ToolRegistry

# Both collaborators send the run's state to the provider, so a long history is
# clipped rather than allowed to grow the prompt without bound.
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
    """The slice of ``LLMClient`` the collaborators need, so tests can supply a double."""

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> LLMCompletion: ...


class LLMDelegate:
    """Answers a delegation with LLM-generated reasoning.

    The Runner records the returned text as the ``delegate_to_llm`` step result,
    so the next route sees it in history; nothing is executed here. A provider
    failure becomes a ``ValueError`` carrying the error category, which the
    Runner lets escape ``run()`` and the service turns into a failed run — a
    delegation that silently produced nothing would be worse.
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
            raise ValueError(f"delegation failed: {exc.category}") from exc
        if not completion.text.strip():
            raise ValueError("the delegate handler returned no result")
        return completion.text


class LLMArgumentResolver:
    """Synthesizes a tool call's arguments from the goal and the run's history.

    The model's output is untrusted input: it is returned unchanged and the
    tool's own pydantic model stays the authority, so a synthesized argument
    fails exactly as a hand-written one would. The schema in the prompt is
    derived from that same model, so the prompt cannot advertise a field the
    tool would refuse.

    A completion that is not a JSON object, is empty, or names no field the tool
    accepts raises rather than degrading to empty arguments — executing a tool
    with nothing would be worse than a stopped run.
    """

    def __init__(self, client: Completer, model: str, tools: ToolRegistry) -> None:
        self._client = client
        self._model = model
        self._tools = tools

    async def resolve(self, action: str, state: TaskState) -> dict[str, Any]:
        try:
            tool = self._tools.get(action)
        except KeyError as exc:
            raise ValueError(f"action {action!r} is not registered") from exc
        try:
            completion = await self._client.complete(
                model=self._model,
                system=_RESOLVER_SYSTEM,
                prompt=_resolver_prompt(action, tool, state),
            )
        except LLMClientError as exc:
            raise ValueError(f"argument synthesis failed: {exc.category}") from exc
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
    """One line per field: type, required-ness, validity constraints, description.

    Only what changes whether the tool accepts the value is rendered — titles
    and `additionalProperties` are noise a model would pattern-match on.
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
    payload = _extract_object(text)
    if not payload:
        raise ValueError("the completion did not contain a JSON object of arguments")
    known = set(model.model_json_schema().get("properties", {}))
    if not known & set(payload):
        raise ValueError(
            f"the completion named no argument the tool accepts: {sorted(payload)}"
        )
    return dict(payload)


def _extract_object(text: str) -> dict[str, Any]:
    """Read the JSON object out of a completion, fenced or not."""
    for candidate in (text, _first_braced_object(text)):
        if candidate is None:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("the completion did not contain a JSON object of arguments")


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

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, Union

from jev_router.clients.llm import LLMCompletion
from jev_router.router import CONTROL_ACTIONS
from jev_router.serialization import jsonable
from jev_router.tools.registry import ToolRegistry

_SYSTEM = (
    "You are the routing baseline of an agent. Given a goal and the candidate "
    "actions, choose the single best next action. Answer with one JSON object "
    "and nothing else."
)

_RESULT_LIMIT = 500


class LLMRouterError(Exception):
    """The baseline could not turn a completion into a valid action choice."""


class Completer(Protocol):
    """The slice of ``LLMClient`` the baseline needs, so tests can supply a double."""

    async def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int | None = ...
    ) -> LLMCompletion: ...


@dataclass(frozen=True)
class LLMRouteDecision:
    """The baseline's answer.

    It deliberately carries no probabilities: an LLM baseline has none, and the
    comparison must not invent them.
    """

    action: str
    reason: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int


class LLMRouter:
    """Routes with an LLM instead of Jev, over the same candidate set.

    The candidate set is built exactly like ``jev_router.Router``'s — the
    registered tools plus the three control actions — so a comparison measures
    the decision, not a different menu.
    """

    def __init__(self, client: Completer, model: str, tools: ToolRegistry) -> None:
        if not model or not model.strip():
            raise ValueError("model must not be empty")
        self._client = client
        self._model = model
        self._tools = tools

    async def route(self, state: Union[str, list[Any], dict[str, Any]]) -> LLMRouteDecision:
        candidates = self._candidates()
        started = time.monotonic()
        completion = await self._client.complete(
            model=self._model,
            system=_SYSTEM,
            prompt=_build_prompt(state, candidates),
        )
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        action, reason = _parse(completion.text, candidates)
        return LLMRouteDecision(
            action=action,
            reason=reason,
            model=completion.model,
            latency_ms=latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )

    def _candidates(self) -> dict[str, str]:
        return {
            **{name: self._tools.get(name).description for name in self._tools.names()},
            **CONTROL_ACTIONS,
        }


def _build_prompt(state: Union[str, list[Any], dict[str, Any]], candidates: Mapping[str, str]) -> str:
    if isinstance(state, dict):
        body = _describe_state(state)
    else:
        body = f"State:\n{json.dumps(jsonable(state), sort_keys=True)}"
    lines = [
        body,
        "",
        "Candidate actions:",
        *[f"- {name}: {description}" for name, description in candidates.items()],
        "",
        'Respond with exactly one JSON object: {"action": "<one candidate>", "reason": "<one sentence>"}',
    ]
    return "\n".join(lines)


def _describe_state(state: Mapping[str, Any]) -> str:
    history = state.get("history") or []
    if isinstance(history, list) and history:
        rendered = []
        for entry in history:
            if not isinstance(entry, Mapping):
                rendered.append(f"- {json.dumps(jsonable(entry), sort_keys=True)}")
                continue
            step = entry.get("step", "?")
            action = entry.get("action", "?")
            result = json.dumps(jsonable(entry.get("result")), sort_keys=True)
            if len(result) > _RESULT_LIMIT:
                result = result[: _RESULT_LIMIT - 3] + "..."
            rendered.append(f"- step {step}: {action} -> {result}")
        history_text = "\n".join(rendered)
    else:
        history_text = "- (none)"
    last_result = json.dumps(jsonable(state.get("last_result")), sort_keys=True)
    if len(last_result) > _RESULT_LIMIT:
        last_result = last_result[: _RESULT_LIMIT - 3] + "..."
    context = json.dumps(jsonable(state.get("context")), sort_keys=True)
    return "\n".join(
        [
            f"Goal: {state.get('goal', '')}",
            f"Step: {state.get('step', 0)}",
            f"Context: {context}",
            "Completed steps:",
            history_text,
            f"Last result: {last_result}",
        ]
    )


def _parse(text: str, candidates: Mapping[str, str]) -> tuple[str, str]:
    payload = _extract_object(text)
    action = payload.get("action")
    reason = payload.get("reason", "")
    if not isinstance(action, str) or action not in candidates:
        raise LLMRouterError(f"the completion did not name a candidate action: {action!r}")
    if not isinstance(reason, str):
        raise LLMRouterError("the completion's reason must be a string")
    return action, reason


def _extract_object(text: str) -> Mapping[str, Any]:
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
    raise LLMRouterError("the completion did not contain a JSON object")


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

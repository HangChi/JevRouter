from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from jev_router.clients.jev import HttpError, JevClient, JevClientConfig
from jev_router.router import RISK_LEVELS, RouteDecision, Router
from jev_router.tools.base import ToolResult
from jev_router.tools.registry import ToolRegistry


class StubTool:
    name = "lookup"
    description = "Read a local record"
    risk = "read"

    def __init__(self) -> None:
        self.executed = False

    def execute(self, input: dict[str, Any]) -> ToolResult:
        self.executed = True
        return ToolResult(tool_name=self.name, output=input)


def config() -> JevClientConfig:
    return JevClientConfig(api_key="test-key")


def response_payload() -> dict[str, Any]:
    return {
        "model": "test-model",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": "lookup",
                "probabilities": {"lookup": 0.7, "ask_user": 0.1, "delegate_to_llm": 0.1, "finish": 0.1},
                "confidence": 0.7,
            },
            "risk": {
                "type": "score",
                "score": 2.0,
                "legend": list(RISK_LEVELS),
                "probabilities": {level: 0.2 for level in RISK_LEVELS},
                "confidence": 0.6,
            },
            "requires_confirmation": {"type": "noul", "noul": 0.8},
            "needs_reasoning": {"type": "noul", "noul": 0.3},
        },
        "usage": {"input_tokens": 20, "output_tokens": 8},
    }


@pytest.mark.asyncio
async def test_router_sends_one_request_and_returns_typed_decision() -> None:
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    tool = StubTool()
    router = Router(
        JevClient(config(), httpx.MockTransport(handler)),
        "test-model",
        ToolRegistry([tool]),
    )
    decision = await router.route({"goal": "find a record"})

    assert len(captured) == 1
    assert captured[0]["state"] == {"goal": "find a record"}
    assert captured[0]["questions"]["next_action"]["criteria"] == {
        "lookup": "Read a local record",
        "ask_user": "More information is required",
        "delegate_to_llm": "The decision requires complex reasoning",
        "finish": "The task is already complete",
    }
    assert captured[0]["questions"]["risk"]["criteria"] == list(RISK_LEVELS)
    assert set(captured[0]["questions"]) == {
        "next_action", "risk", "requires_confirmation", "needs_reasoning"
    }
    assert decision == RouteDecision(
        action="lookup",
        confidence=0.7,
        risk=2.0,
        risk_confidence=0.6,
        requires_confirmation=0.8,
        needs_reasoning=0.3,
        model="test-model",
    )
    assert not tool.executed


@pytest.mark.asyncio
async def test_router_with_empty_registry_offers_control_actions() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        payload = response_payload()
        payload["answers"]["next_action"]["choice"] = "finish"
        payload["answers"]["next_action"]["probabilities"] = {
            "ask_user": 0.1,
            "delegate_to_llm": 0.1,
            "finish": 0.8,
        }
        return httpx.Response(200, json=payload)

    decision = await Router(
        JevClient(config(), httpx.MockTransport(handler)), "test-model", ToolRegistry()
    ).route("done")

    assert captured["questions"]["next_action"]["criteria"] == {
        "ask_user": "More information is required",
        "delegate_to_llm": "The decision requires complex reasoning",
        "finish": "The task is already complete",
    }
    assert decision.action == "finish"


@pytest.mark.asyncio
async def test_router_propagates_client_errors() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    router = Router(JevClient(config(), httpx.MockTransport(handler)), "test-model", ToolRegistry())
    with pytest.raises(HttpError):
        await router.route({})

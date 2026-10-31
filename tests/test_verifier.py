from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any

import httpx
import pytest

from jev_router.clients.jev import (
    HttpError,
    JevClient,
    JevClientConfig,
    ResponseDecodingError,
    ResponseValidationError,
)
from jev_router.state import TaskState
from jev_router.verifier import QUALITY_LEVELS, VerificationDecision, Verifier


def config() -> JevClientConfig:
    return JevClientConfig(api_key="test-key")


def response_payload() -> dict[str, Any]:
    return {
        "model": "test-model",
        "answers": {
            "task_complete": {"type": "noul", "noul": 0.82},
            "result_quality": {
                "type": "score",
                "score": 3.0,
                "legend": list(QUALITY_LEVELS),
                "probabilities": {level: 0.25 for level in QUALITY_LEVELS},
                "confidence": 0.6,
            },
        },
        "usage": {"input_tokens": 18, "output_tokens": 6},
    }


def completed_state() -> TaskState:
    return TaskState(
        goal="Find tomorrow's weather in Tokyo",
        context={"locale": "ja-JP"},
    ).advance("web_search", {"temperature": "24C", "weather": "rain"})


@pytest.mark.asyncio
async def test_verifier_sends_one_request_with_both_questions() -> None:
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    verifier = Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model")
    decision = await verifier.verify(completed_state())

    assert len(captured) == 1
    questions = captured[0]["questions"]
    assert set(questions) == {"task_complete", "result_quality"}
    assert questions["task_complete"] == {
        "type": "noul",
        "instructions": "Does the current result satisfy the user goal?",
    }
    assert questions["result_quality"] == {
        "type": "score",
        "instructions": "Rate how well the result satisfies the goal.",
        "criteria": list(QUALITY_LEVELS),
    }
    state = captured[0]["state"]
    assert state["goal"] == "Find tomorrow's weather in Tokyo"
    assert state["step"] == 1
    assert state["action"] == "web_search"
    assert state["result"] == {"temperature": "24C", "weather": "rain"}
    assert state["context"] == {"locale": "ja-JP"}
    assert state["history"] == [
        {
            "step": 1,
            "action": "web_search",
            "result": {"temperature": "24C", "weather": "rain"},
        }
    ]
    assert decision == VerificationDecision(
        completion_probability=0.82,
        quality_score=3.0,
        quality_confidence=0.6,
        quality_legend=QUALITY_LEVELS,
        model="test-model",
    )


@pytest.mark.asyncio
async def test_verifier_sends_json_plain_state_for_dict_snapshots() -> None:
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    state = TaskState(goal="g", context={"nested": {"tags": ("a", "b")}}).advance(
        "calculator", {"value": 4}
    )
    await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
        state
    )

    payload = captured[0]
    assert payload["state"]["context"] == {"nested": {"tags": ["a", "b"]}}
    assert payload["state"]["result"] == {"value": 4}
    assert payload["state"]["history"][0]["result"] == {"value": 4}
    json.dumps(payload, allow_nan=False)


@pytest.mark.asyncio
async def test_verifier_returns_model_from_response() -> None:
    payload = response_payload()
    payload["model"] = "jev-2"

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    decision = await Verifier(
        JevClient(config(), httpx.MockTransport(handler)), "test-model"
    ).verify(completed_state())

    assert decision.model == "jev-2"


def test_verification_decision_is_immutable() -> None:
    decision = VerificationDecision(
        completion_probability=0.5,
        quality_score=2.0,
        quality_confidence=0.4,
        quality_legend=QUALITY_LEVELS,
        model="test-model",
    )
    with pytest.raises(FrozenInstanceError):
        decision.completion_probability = 0.9  # type: ignore[misc]


@pytest.mark.asyncio
async def test_verifier_rejects_state_without_completed_step_before_io() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=response_payload())

    with pytest.raises(ValueError, match="至少需要一个已完成的步骤"):
        await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
            TaskState(goal="Find tomorrow's weather in Tokyo")
        )
    assert not called


@pytest.mark.asyncio
async def test_verifier_rejects_state_without_latest_result_before_io() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=response_payload())

    with pytest.raises(ValueError, match="最新结果"):
        await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
            TaskState(goal="Find tomorrow's weather in Tokyo").advance("web_search")
        )
    assert not called


@pytest.mark.asyncio
async def test_verifier_propagates_http_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(HttpError):
        await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
            completed_state()
        )


@pytest.mark.asyncio
async def test_verifier_propagates_decoding_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    with pytest.raises(ResponseDecodingError):
        await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
            completed_state()
        )


@pytest.mark.asyncio
async def test_verifier_propagates_validation_failure() -> None:
    payload = response_payload()
    payload["answers"]["result_quality"]["legend"] = ["Not useful", "Wrong legend"]

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ResponseValidationError):
        await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(
            completed_state()
        )


@pytest.mark.asyncio
async def test_verifier_does_not_mutate_state() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload())

    state = completed_state()
    before = (state.goal, state.step, state.context, state.history, state.last_result)

    await Verifier(JevClient(config(), httpx.MockTransport(handler)), "test-model").verify(state)

    assert (state.goal, state.step, state.context, state.history, state.last_result) == before
    assert state == completed_state()

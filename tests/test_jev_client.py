from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from jev_router.clients.jev import (
    ChoiceAnswer,
    ChoiceQuestion,
    ConfigurationError,
    HttpError,
    JevClient,
    JevClientConfig,
    NoulAnswer,
    NoulQuestion,
    RequestValidationError,
    ResponseDecodingError,
    ResponseValidationError,
    ScoreAnswer,
    ScoreQuestion,
    TransportError,
)
from jev_router.router import RISK_LEVELS

API_KEY = "test-secret-do-not-leak"


def config() -> JevClientConfig:
    return JevClientConfig(api_key=API_KEY)


def answer_payload() -> dict[str, Any]:
    return {"model": "test-model", "answers": {"ready": {"type": "noul", "noul": 0.91}, "route": {"type": "choice", "choice": "search", "probabilities": {"search": 0.8, "finish": 0.2}, "confidence": 0.8}, "risk": {"type": "score", "score": 1.4, "legend": ["low", "medium", "high"], "probabilities": {"low": 0.2, "medium": 0.7, "high": 0.1}, "confidence": 0.7}}, "usage": {"input_tokens": 42, "output_tokens": 9}}


def mixed_questions() -> Mapping[str, Any]:
    return {
        "ready": NoulQuestion(instructions="Is the state ready?"),
        "route": ChoiceQuestion(
            instructions="Choose an action.",
            criteria={"search": "Search", "finish": "Finish"},
        ),
        "risk": ScoreQuestion(
            instructions="Rate risk.",
            criteria=["low", "medium", "high"],
        ),
    }


@pytest.mark.asyncio
async def test_base_url_path_prefix_is_preserved() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/proxy/v1/systemone"
        return httpx.Response(200, json=answer_payload())

    client = JevClient(
        JevClientConfig(api_key=API_KEY, base_url="https://example.test/proxy/"),
        httpx.MockTransport(handler),
    )
    await client.systemone(model="test-model", state={}, questions=mixed_questions())


@pytest.mark.asyncio
async def test_systemone_sends_documented_payload_and_parses_mixed_answers() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=answer_payload())

    client = JevClient(config(), httpx.MockTransport(handler))
    result = await client.systemone(
        model="test-model",
        state={"goal": "complete", "items": [1, 2]},
        questions=mixed_questions(),
    )

    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["headers"]["authorization"] == "Bearer " + API_KEY
    assert captured["body"] == {
        "model": "test-model",
        "state": {"goal": "complete", "items": [1, 2]},
        "questions": {
            "ready": {"type": "noul", "instructions": "Is the state ready?"},
            "route": {
                "type": "choice",
                "instructions": "Choose an action.",
                "criteria": {"search": "Search", "finish": "Finish"},
            },
            "risk": {
                "type": "score",
                "instructions": "Rate risk.",
                "criteria": ["low", "medium", "high"],
            },
        },
    }
    assert isinstance(result.answers["ready"], NoulAnswer)
    assert isinstance(result.answers["route"], ChoiceAnswer)
    assert isinstance(result.answers["risk"], ScoreAnswer)
    assert result.answers["ready"].noul == 0.91
    assert result.answers["route"].choice == "search"
    assert result.answers["risk"].score == 1.4
    assert result.usage.input_tokens == 42


@pytest.mark.asyncio
async def test_invalid_request_is_rejected_before_transport() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client = JevClient(config(), httpx.MockTransport(handler))
    with pytest.raises(RequestValidationError):
        await client.systemone(model="", state={}, questions={})
    with pytest.raises(RequestValidationError):
        await client.systemone(model="m", state={"bad": object()}, questions=mixed_questions())
    with pytest.raises(RequestValidationError):
        await client.systemone(
            model="m",
            state={},
            questions={"bad": NoulQuestion(instructions={"bad": object()})},
        )
    assert not called


def test_question_criteria_limits_and_sensitive_config() -> None:
    with pytest.raises(ValidationError):
        ChoiceQuestion(instructions="pick", criteria={})
    with pytest.raises(ValidationError):
        ScoreQuestion(instructions="score", criteria=["only-one"])
    with pytest.raises(ConfigurationError):
        JevClientConfig(api_key="", base_url="https://api.typesafe.ai")
    assert API_KEY not in repr(config())


def test_answer_probability_constraints() -> None:
    with pytest.raises(ValidationError):
        NoulAnswer(type="noul", noul=1.1)
    with pytest.raises(ValidationError):
        ChoiceAnswer(
            type="choice",
            choice="a",
            probabilities={"a": 0.2, "b": 0.2},
            confidence=0.2,
        )


@pytest.mark.asyncio
async def test_mismatched_response_is_sanitized() -> None:
    payload = answer_payload()
    payload["answers"]["route"]["choice"] = "not-submitted"

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ResponseValidationError) as error:
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )
    assert API_KEY not in str(error.value)


@pytest.mark.parametrize("status_code", [401, 422, 429, 529, 500])
@pytest.mark.asyncio
async def test_http_failures_are_typed_and_do_not_leak_secrets(status_code: int) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text=API_KEY)

    with pytest.raises(HttpError) as error:
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )
    assert error.value.status_code == status_code
    assert API_KEY not in str(error.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_invalid_json_response_is_typed() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with pytest.raises(ResponseDecodingError):
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )


@pytest.mark.asyncio
async def test_transport_failure_is_typed_and_sanitized() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(API_KEY)

    with pytest.raises(TransportError) as error:
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )
    assert API_KEY not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_failure_is_typed() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("internal timeout details")

    with pytest.raises(TransportError, match="超时"):
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )


def test_environment_configuration_requires_api_key() -> None:
    with pytest.raises(ConfigurationError, match="JEV_API_KEY"):
        JevClientConfig.from_env({})

    loaded = JevClientConfig.from_env(
        {"JEV_API_KEY": API_KEY, "JEV_BASE_URL": "https://example.test", "JEV_TIMEOUT_SECONDS": "12"}
    )
    assert loaded.base_url == "https://example.test"
    assert loaded.timeout_seconds == 12


# 取自对 jev-latest 的一次真实 POST /v1/systemone。score 类型的答案携带的是
# 以索引为键的 legend 和 probabilities，而第一阶段的替身从未产生过这种形状：
# 所有离线测试都通过，真实运行却在校验时失败。这份测试夹具是观察到的契约，
# 而不是假定的契约。
LIVE_SCORE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "next_action": {
            "type": "choice",
            "choice": "calculator",
            "confidence": 0.99,
            "probabilities": {
                "ask_user": 0.0,
                "calculator": 0.99,
                "finish": 0.01,
                "delegate_to_llm": 0.0,
            },
        },
        "risk": {
            "type": "score",
            "score": 0.0,
            "confidence": 1.0,
            "legend": {
                "0": "No meaningful side effects",
                "1": "Minor reversible side effects",
                "2": "Meaningful but reversible action",
                "3": "External or consequential action",
                "4": "Potentially destructive or irreversible action",
            },
            "probabilities": {"0": 1.0, "1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0},
        },
        "requires_confirmation": {"type": "noul", "noul": 0.12},
        "needs_reasoning": {"type": "noul", "noul": 0.04},
    },
    "usage": {"input_tokens": 485, "output_tokens": 100},
}


def live_questions() -> dict[str, Any]:
    return {
        "next_action": ChoiceQuestion(
            instructions="Choose the best next action.",
            criteria={
                "calculator": "Evaluate a bounded arithmetic expression.",
                "ask_user": "More information is required",
                "delegate_to_llm": "The decision requires complex reasoning",
                "finish": "The task is already complete",
            },
        ),
        "risk": ScoreQuestion(
            instructions="Rate the risk.",
            criteria=list(RISK_LEVELS),
        ),
        "requires_confirmation": NoulQuestion(instructions="Should the user confirm?"),
        "needs_reasoning": NoulQuestion(instructions="Does this need deep reasoning?"),
    }


@pytest.mark.asyncio
async def test_a_live_score_answer_is_accepted_and_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LIVE_SCORE_RESPONSE)

    client = JevClient(config(), httpx.MockTransport(handler))
    result = await client.systemone(
        model="jev-latest", state={"goal": "what is 2 + 2?"}, questions=live_questions()
    )

    risk = result.answers["risk"]
    assert isinstance(risk, ScoreAnswer)
    assert risk.legend == list(RISK_LEVELS)
    assert set(risk.probabilities) == set(RISK_LEVELS)
    assert math.isclose(sum(risk.probabilities.values()), 1.0)
    assert risk.probabilities["No meaningful side effects"] == 1.0
    assert risk.score == 0.0
    assert (result.usage.input_tokens, result.usage.output_tokens) == (485, 100)


def test_a_list_legend_still_validates() -> None:
    """离线测试夹具所用的、以标签为键的形状仍然被接受。"""
    answer = ScoreAnswer.model_validate(
        {
            "type": "score",
            "score": 2.0,
            "legend": ["low", "medium", "high"],
            "probabilities": {"low": 0.2, "medium": 0.7, "high": 0.1},
            "confidence": 0.7,
        }
    )
    assert answer.legend == ["low", "medium", "high"]


@pytest.mark.asyncio
async def test_a_score_answer_keyed_neither_by_index_nor_by_label_is_refused() -> None:
    """legend 会被归一化，因此捕获不匹配的是 criteria 校验。"""
    payload = json.loads(json.dumps(LIVE_SCORE_RESPONSE))
    payload["answers"]["risk"]["probabilities"] = {"a": 0.5, "b": 0.5}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = JevClient(config(), httpx.MockTransport(handler))
    with pytest.raises(ResponseValidationError):
        await client.systemone(
            model="jev-latest", state={"goal": "x"}, questions=live_questions()
        )


@pytest.mark.asyncio
async def test_a_rounded_distribution_is_accepted() -> None:
    """提供方会四舍五入到两位小数，因此 8 路求和为 0.99 是合法的。"""
    payload = answer_payload()
    payload["answers"]["route"]["probabilities"] = {
        "search": 0.33,
        "finish": 0.33,
        "retry": 0.33,
    }
    payload["answers"]["route"]["choice"] = "search"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    questions = mixed_questions()
    questions["route"] = ChoiceQuestion(
        instructions="Choose an action.",
        criteria={"search": "Search", "finish": "Finish", "retry": "Retry"},
    )
    result = await JevClient(config(), httpx.MockTransport(handler)).systemone(
        model="test-model", state={}, questions=questions
    )
    assert result.answers["route"].choice == "search"


@pytest.mark.asyncio
async def test_a_broken_distribution_names_the_check_that_failed() -> None:
    payload = answer_payload()
    payload["answers"]["route"]["probabilities"] = {"search": 0.2, "finish": 0.2}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ResponseValidationError) as excinfo:
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )
    assert "之和必须为 1" in str(excinfo.value)
    assert excinfo.value.category == "response_validation"


@pytest.mark.asyncio
async def test_a_mismatched_answer_set_names_the_check_that_failed() -> None:
    payload = answer_payload()
    del payload["answers"]["risk"]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ResponseValidationError) as excinfo:
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )
    assert "问题必须与请求中的问题一致" in str(excinfo.value)

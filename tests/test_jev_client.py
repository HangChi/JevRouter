from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping

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

API_KEY = "test-secret-do-not-leak"


def config() -> JevClientConfig:
    return JevClientConfig(api_key=API_KEY)


def answer_payload() -> Dict[str, Any]:
    return {
        "model": "test-model",
        "answers": {
            "ready": {"type": "noul", "noul": 0.91},
            "route": {
                "type": "choice",
                "choice": "search",
                "probabilities": {"search": 0.8, "finish": 0.2},
                "confidence": 0.8,
            },
            "risk": {
                "type": "score",
                "score": 1.4,
                "legend": ["low", "medium", "high"],
                "probabilities": {"low": 0.2, "medium": 0.7, "high": 0.1},
                "confidence": 0.7,
            },
        },
        "usage": {"input_tokens": 42, "output_tokens": 9},
    }


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
async def test_systemone_sends_documented_payload_and_parses_mixed_answers() -> None:
    captured: Dict[str, Any] = {}

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

    with pytest.raises(TransportError, match="timed out"):
        await JevClient(config(), httpx.MockTransport(handler)).systemone(
            model="test-model", state={}, questions=mixed_questions()
        )


def test_environment_configuration_requires_api_key() -> None:
    with pytest.raises(ConfigurationError, match="JEV_API_KEY is required"):
        JevClientConfig.from_env({})

    loaded = JevClientConfig.from_env(
        {"JEV_API_KEY": API_KEY, "JEV_BASE_URL": "https://example.test", "JEV_TIMEOUT_SECONDS": "12"}
    )
    assert loaded.base_url == "https://example.test"
    assert loaded.timeout_seconds == 12

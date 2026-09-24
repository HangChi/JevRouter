from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from jev_router.clients.llm import (
    LLMClient,
    LLMClientConfig,
    LLMConfigurationError,
    LLMHttpError,
    LLMRequestValidationError,
    LLMResponseDecodingError,
    LLMResponseValidationError,
    LLMTransportError,
)

API_KEY = "llm-secret-do-not-leak"
MODEL = "claude-sonnet-4-5"


def config(**overrides: Any) -> LLMClientConfig:
    values: dict[str, Any] = {"api_key": API_KEY}
    values.update(overrides)
    return LLMClientConfig(**values)


def response_payload(text: str = "ok") -> dict[str, Any]:
    return {
        "model": MODEL,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 120, "output_tokens": 8},
    }


def messages_response(text: str = "ok", **usage: int) -> httpx.Response:
    payload = response_payload(text)
    payload["usage"].update(usage)
    return httpx.Response(200, json=payload)


@pytest.mark.asyncio
async def test_complete_sends_documented_payload_and_headers() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return messages_response("the answer")

    client = LLMClient(config(), httpx.MockTransport(handler))
    result = await client.complete(
        model=MODEL, system="be terse", prompt="what is 2+2?", max_tokens=256
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == API_KEY
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"] == {
        "model": MODEL,
        "max_tokens": 256,
        "system": "be terse",
        "messages": [{"role": "user", "content": "what is 2+2?"}],
    }
    assert result.text == "the answer"
    assert result.model == MODEL
    assert (result.input_tokens, result.output_tokens) == (120, 8)


@pytest.mark.asyncio
async def test_base_url_path_prefix_is_preserved() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gateway.test/proxy/v1/messages"
        return messages_response()

    client = LLMClient(
        config(base_url="https://gateway.test/proxy/"), httpx.MockTransport(handler)
    )
    await client.complete(model=MODEL, system="s", prompt="p")


@pytest.mark.asyncio
async def test_default_max_tokens_come_from_config() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return messages_response()

    client = LLMClient(config(max_tokens=77), httpx.MockTransport(handler))
    await client.complete(model=MODEL, system="s", prompt="p")
    assert captured["body"]["max_tokens"] == 77


@pytest.mark.asyncio
async def test_non_success_status_raises_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMHttpError) as excinfo:
        await client.complete(model=MODEL, system="s", prompt="p")
    assert excinfo.value.category == "http"
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_transport_failure_raises_transport_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMTransportError) as excinfo:
        await client.complete(model=MODEL, system="s", prompt="p")
    assert excinfo.value.category == "transport"


@pytest.mark.asyncio
async def test_invalid_json_raises_decoding_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMResponseDecodingError):
        await client.complete(model=MODEL, system="s", prompt="p")


@pytest.mark.asyncio
async def test_missing_text_block_raises_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"model": MODEL, "content": [{"type": "tool_use"}], "usage": {"input_tokens": 1, "output_tokens": 1}}
        )

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMResponseValidationError):
        await client.complete(model=MODEL, system="s", prompt="p")


@pytest.mark.asyncio
async def test_schema_mismatch_raises_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": MODEL, "content": "not-a-list", "usage": {}})

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMResponseValidationError):
        await client.complete(model=MODEL, system="s", prompt="p")


@pytest.mark.asyncio
async def test_negative_usage_raises_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": MODEL,
                "content": [{"type": "text", "text": "x"}],
                "usage": {"input_tokens": -5, "output_tokens": 1},
            },
        )

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMResponseValidationError):
        await client.complete(model=MODEL, system="s", prompt="p")


@pytest.mark.asyncio
async def test_blank_model_or_prompt_is_rejected_before_the_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be sent")

    client = LLMClient(config(), httpx.MockTransport(handler))
    with pytest.raises(LLMRequestValidationError):
        await client.complete(model="  ", system="s", prompt="p")
    with pytest.raises(LLMRequestValidationError):
        await client.complete(model=MODEL, system="s", prompt="   ")


def test_blank_key_is_rejected() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig(api_key="   ")


def test_non_https_base_url_is_rejected() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig(api_key=API_KEY, base_url="http://insecure.test")


def test_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig(api_key=API_KEY, timeout_seconds=0)


def test_non_positive_max_tokens_is_rejected() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig(api_key=API_KEY, max_tokens=0)


def test_blank_api_version_is_rejected() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig(api_key=API_KEY, api_version=" ")


def test_from_env_reads_documented_variables() -> None:
    resolved = LLMClientConfig.from_env(
        {
            "LLM_API_KEY": API_KEY,
            "LLM_BASE_URL": "https://gateway.test/",
            "LLM_TIMEOUT_SECONDS": "12",
            "LLM_MAX_TOKENS": "2048",
            "LLM_API_VERSION": "2024-01-01",
        }
    )
    assert resolved.base_url == "https://gateway.test/"
    assert resolved.timeout_seconds == 12.0
    assert resolved.max_tokens == 2048
    assert resolved.api_version == "2024-01-01"


def test_from_env_defaults_to_the_documented_provider() -> None:
    resolved = LLMClientConfig.from_env({"LLM_API_KEY": API_KEY})
    assert resolved.base_url == "https://api.anthropic.com"
    assert resolved.max_tokens == 1024


def test_from_env_requires_a_key() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig.from_env({})


def test_from_env_rejects_non_numeric_timeout() -> None:
    with pytest.raises(LLMConfigurationError):
        LLMClientConfig.from_env({"LLM_API_KEY": API_KEY, "LLM_TIMEOUT_SECONDS": "soon"})


def test_config_repr_hides_the_key() -> None:
    assert API_KEY not in repr(config())


STEPFUN_BASE = "https://api.stepfun.com/step_plan/v1"


def chat_config(**overrides: Any) -> LLMClientConfig:
    values: dict[str, Any] = {
        "api_key": API_KEY,
        "base_url": STEPFUN_BASE,
        "api_style": "chat_completions",
    }
    values.update(overrides)
    return LLMClientConfig(**values)


def chat_response(text: str = "ok") -> dict[str, Any]:
    return {
        "model": "step-5-preview",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 210, "completion_tokens": 18, "total_tokens": 228},
    }


@pytest.mark.asyncio
async def test_chat_completions_sends_the_openai_shape() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=chat_response("the answer"))

    client = LLMClient(chat_config(), httpx.MockTransport(handler))
    result = await client.complete(
        model="step-5-preview", system="be terse", prompt="what is 2+2?", max_tokens=256
    )

    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/chat/completions"
    assert captured["headers"]["authorization"] == f"Bearer {API_KEY}"
    assert "x-api-key" not in captured["headers"]
    assert captured["body"] == {
        "model": "step-5-preview",
        "max_tokens": 256,
        "messages": [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "what is 2+2?"},
        ],
    }
    assert result.text == "the answer"
    assert result.model == "step-5-preview"
    assert (result.input_tokens, result.output_tokens) == (210, 18)


@pytest.mark.asyncio
async def test_chat_completions_maps_the_error_taxonomy() -> None:
    async def http_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = LLMClient(chat_config(), httpx.MockTransport(http_handler))
    with pytest.raises(LLMHttpError) as excinfo:
        await client.complete(model="m", system="s", prompt="p")
    assert excinfo.value.status_code == 401

    async def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "m", "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    client = LLMClient(chat_config(), httpx.MockTransport(empty_handler))
    with pytest.raises(LLMResponseValidationError):
        await client.complete(model="m", system="s", prompt="p")


def test_an_unknown_api_style_is_refused() -> None:
    with pytest.raises(LLMConfigurationError, match="LLM_API_STYLE"):
        LLMClientConfig(api_key=API_KEY, api_style="grpc")  # type: ignore[arg-type]


def test_from_env_reads_the_api_style() -> None:
    resolved = LLMClientConfig.from_env(
        {
            "LLM_API_KEY": API_KEY,
            "LLM_BASE_URL": STEPFUN_BASE,
            "LLM_API_STYLE": "chat_completions",
        }
    )
    assert resolved.api_style == "chat_completions"


def test_from_env_defaults_to_the_messages_style() -> None:
    assert LLMClientConfig.from_env({"LLM_API_KEY": API_KEY}).api_style == "messages"

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class LLMClientError(Exception):
    def __init__(self, category: str, message: str, *, status_code: Optional[int] = None) -> None:
        self.category = category
        self.status_code = status_code
        super().__init__(message)


class LLMConfigurationError(LLMClientError):
    def __init__(self, message: str) -> None:
        super().__init__("configuration", message)


class LLMRequestValidationError(LLMClientError):
    def __init__(self, message: str) -> None:
        super().__init__("request_validation", message)


class LLMTransportError(LLMClientError):
    def __init__(self, message: str) -> None:
        super().__init__("transport", message)


class LLMHttpError(LLMClientError):
    def __init__(self, status_code: int) -> None:
        super().__init__("http", "LLM 服务返回了失败状态", status_code=status_code)


class LLMResponseDecodingError(LLMClientError):
    def __init__(self) -> None:
        super().__init__("response_decoding", "LLM 服务返回了无效的 JSON")


class LLMResponseValidationError(LLMClientError):
    def __init__(self) -> None:
        super().__init__("response_validation", "LLM 服务的响应与预期的结构不匹配")


@dataclass(frozen=True)
class LLMClientConfig:
    """LLM 适配器的连接设置。

    与 ``JevClientConfig`` 对应：所有内容都在构造时校验，因此配置错误的
    部署会在第一次请求补全之前就失败。

    ``api_style`` 选择线格式。``messages`` 是 Anthropic Messages API
    （``POST /v1/messages``、``x-api-key``）；``chat_completions`` 是许多
    网关提供的 OpenAI 兼容形状（``POST /chat/completions``、
    ``Authorization: Bearer``），其 base URL 已带上版本段。两者产出相同的
    ``LLMCompletion``，因此消费方不关心部署用的是哪一种。
    """

    api_key: str = field(repr=False)
    base_url: str = "https://api.anthropic.com"
    timeout_seconds: float = 30.0
    max_tokens: int = 1024
    api_version: str = "2023-06-01"
    api_style: Literal["messages", "chat_completions"] = "messages"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise LLMConfigurationError("LLM_API_KEY 不得为空")
        if not self.base_url.startswith("https://"):
            raise LLMConfigurationError("LLM_BASE_URL 必须使用 HTTPS")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS 必须是有限的正数")
        if self.max_tokens < 1:
            raise LLMConfigurationError("LLM_MAX_TOKENS 必须为正数")
        if not self.api_version.strip():
            raise LLMConfigurationError("LLM_API_VERSION 不得为空")
        if self.api_style not in ("messages", "chat_completions"):
            raise LLMConfigurationError("LLM_API_STYLE 必须是 'messages' 或 'chat_completions'")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> LLMClientConfig:
        env = os.environ if environ is None else environ
        key = env.get("LLM_API_KEY", "")
        if not key:
            raise LLMConfigurationError("必须提供 LLM_API_KEY")
        base_url = env.get("LLM_BASE_URL", "https://api.anthropic.com")
        try:
            timeout = float(env.get("LLM_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS 必须是数字") from exc
        try:
            max_tokens = int(env.get("LLM_MAX_TOKENS", "1024"))
        except ValueError as exc:
            raise LLMConfigurationError("LLM_MAX_TOKENS 必须是整数") from exc
        return cls(
            api_key=key,
            base_url=base_url,
            timeout_seconds=timeout,
            max_tokens=max_tokens,
            api_version=env.get("LLM_API_VERSION", "2023-06-01"),
            api_style=env.get("LLM_API_STYLE", "messages"),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class LLMCompletion:
    """一次补全，附带对比指标所需的 token 计数。"""

    text: str
    model: str
    input_tokens: int
    output_tokens: int


class _ContentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    text: Optional[str] = None


class _Usage(BaseModel):
    model_config = ConfigDict(extra="allow")

    input_tokens: int
    output_tokens: int

    @field_validator("input_tokens", "output_tokens")
    @classmethod
    def validate_tokens(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token 数不得为负数")
        return value


class _MessagesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    content: list[_ContentBlock]
    usage: _Usage


class _ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: str


class _ChatChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: _ChatMessage


class _ChatUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_tokens: int
    completion_tokens: int

    @field_validator("prompt_tokens", "completion_tokens")
    @classmethod
    def validate_tokens(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token 数不得为负数")
        return value


class _ChatCompletionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    choices: list[_ChatChoice]
    usage: _ChatUsage


@dataclass
class LLMClient:
    """极简 LLM 客户端，支持两种线格式。

    一次 ``complete`` 调用、一个可注入的 transport、不做重试——与
    ``JevClient`` 形状一致，两个适配器因此以相同方式失败，且无需凭据即可
    测试。配置上的 ``api_style`` 决定请求与响应的形状；下游看到的只有
    ``LLMCompletion``。
    """

    config: LLMClientConfig
    transport: Optional[httpx.AsyncBaseTransport] = None

    async def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_tokens: Optional[int] = None,
    ) -> LLMCompletion:
        if not model or not model.strip():
            raise LLMRequestValidationError("必须提供 model")
        if not prompt.strip():
            raise LLMRequestValidationError("prompt 不得为空")
        tokens = self.config.max_tokens if max_tokens is None else max_tokens
        if tokens < 1:
            raise LLMRequestValidationError("max_tokens 必须为正数")
        if self.config.api_style == "chat_completions":
            url, headers, payload = self._chat_request(model, system, prompt, tokens)
        else:
            url, headers, payload = self._messages_request(model, system, prompt, tokens)
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMTransportError("LLM 服务请求超时") from exc
            except httpx.RequestError as exc:
                raise LLMTransportError("LLM 服务请求失败") from exc

        if response.is_error:
            raise LLMHttpError(response.status_code)
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseDecodingError() from exc
        if self.config.api_style == "chat_completions":
            return self._chat_completion(payload)
        return self._messages_completion(payload)

    def _messages_request(
        self, model: str, system: str, prompt: str, tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = urljoin(self.config.base_url.rstrip("/") + "/", "v1/messages")
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.api_version,
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        return url, headers, payload

    def _chat_request(
        self, model: str, system: str, prompt: str, tokens: int
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        # 这种风格下 base URL 已经包含版本段。
        url = urljoin(self.config.base_url.rstrip("/") + "/", "chat/completions")
        headers = {
            "Authorization": "Bearer " + self.config.api_key,
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        return url, headers, payload

    def _messages_completion(self, payload: Any) -> LLMCompletion:
        try:
            result = _MessagesResponse.model_validate(payload)
        except ValidationError as exc:
            raise LLMResponseValidationError() from exc
        text = next(
            (
                block.text
                for block in result.content
                if block.type == "text" and block.text is not None
            ),
            None,
        )
        if text is None:
            raise LLMResponseValidationError()
        return LLMCompletion(
            text=text,
            model=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )

    def _chat_completion(self, payload: Any) -> LLMCompletion:
        try:
            result = _ChatCompletionsResponse.model_validate(payload)
        except ValidationError as exc:
            raise LLMResponseValidationError() from exc
        if not result.choices:
            raise LLMResponseValidationError()
        return LLMCompletion(
            text=result.choices[0].message.content,
            model=result.model,
            input_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.completion_tokens,
        )

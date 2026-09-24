from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Optional
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
        super().__init__("http", "LLM service returned an unsuccessful status", status_code=status_code)


class LLMResponseDecodingError(LLMClientError):
    def __init__(self) -> None:
        super().__init__("response_decoding", "LLM service returned invalid JSON")


class LLMResponseValidationError(LLMClientError):
    def __init__(self) -> None:
        super().__init__("response_validation", "LLM service response did not match the expected schema")


@dataclass(frozen=True)
class LLMClientConfig:
    """Connection settings for the LLM adapter.

    Mirrors ``JevClientConfig``: everything is validated at construction so a
    misconfigured deployment fails before the first completion is requested. The
    provider shape is the Anthropic Messages API; a different gateway is a base
    URL change, a different provider is a different client.
    """

    api_key: str = field(repr=False)
    base_url: str = "https://api.anthropic.com"
    timeout_seconds: float = 30.0
    max_tokens: int = 1024
    api_version: str = "2023-06-01"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise LLMConfigurationError("LLM_API_KEY must not be empty")
        if not self.base_url.startswith("https://"):
            raise LLMConfigurationError("LLM_BASE_URL must use HTTPS")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be a finite positive number")
        if self.max_tokens < 1:
            raise LLMConfigurationError("LLM_MAX_TOKENS must be positive")
        if not self.api_version.strip():
            raise LLMConfigurationError("LLM_API_VERSION must not be empty")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> LLMClientConfig:
        env = os.environ if environ is None else environ
        key = env.get("LLM_API_KEY", "")
        if not key:
            raise LLMConfigurationError("LLM_API_KEY is required")
        base_url = env.get("LLM_BASE_URL", "https://api.anthropic.com")
        try:
            timeout = float(env.get("LLM_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be numeric") from exc
        try:
            max_tokens = int(env.get("LLM_MAX_TOKENS", "1024"))
        except ValueError as exc:
            raise LLMConfigurationError("LLM_MAX_TOKENS must be an integer") from exc
        return cls(
            api_key=key,
            base_url=base_url,
            timeout_seconds=timeout,
            max_tokens=max_tokens,
            api_version=env.get("LLM_API_VERSION", "2023-06-01"),
        )


@dataclass(frozen=True)
class LLMCompletion:
    """One completion, with the token counts the comparison metrics need."""

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
            raise ValueError("token counts must not be negative")
        return value


class _MessagesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    content: list[_ContentBlock]
    usage: _Usage


@dataclass
class LLMClient:
    """Minimal Anthropic Messages API client.

    One ``complete`` call, one injectable transport, no retries — the same shape
    as ``JevClient`` so both adapters fail the same way and are testable without
    a credential.
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
            raise LLMRequestValidationError("model is required")
        if not prompt.strip():
            raise LLMRequestValidationError("prompt must not be empty")
        tokens = self.config.max_tokens if max_tokens is None else max_tokens
        if tokens < 1:
            raise LLMRequestValidationError("max_tokens must be positive")
        payload = {
            "model": model,
            "max_tokens": tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
            try:
                response = await client.post(
                    urljoin(self.config.base_url.rstrip("/") + "/", "v1/messages"),
                    headers={
                        "x-api-key": self.config.api_key,
                        "anthropic-version": self.config.api_version,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise LLMTransportError("LLM service request timed out") from exc
            except httpx.RequestError as exc:
                raise LLMTransportError("LLM service request failed") from exc

        if response.is_error:
            raise LLMHttpError(response.status_code)
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMResponseDecodingError() from exc
        try:
            result = _MessagesResponse.model_validate(payload)
        except ValidationError as exc:
            raise LLMResponseValidationError() from exc
        text = next(
            (block.text for block in result.content if block.type == "text" and block.text is not None),
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

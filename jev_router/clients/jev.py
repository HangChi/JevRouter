from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional, Union
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

JSONValue = Union[None, bool, int, float, str, list[Any], dict[str, Any]]
QuestionInstructions = Union[str, dict[str, Any], list[Any]]


class JevClientError(Exception):
    def __init__(self, category: str, message: str, *, status_code: Optional[int] = None) -> None:
        self.category = category
        self.status_code = status_code
        super().__init__(message)


class ConfigurationError(JevClientError):
    def __init__(self, message: str) -> None:
        super().__init__("configuration", message)


class RequestValidationError(JevClientError):
    def __init__(self, message: str) -> None:
        super().__init__("request_validation", message)


class TransportError(JevClientError):
    def __init__(self, message: str) -> None:
        super().__init__("transport", message)


class HttpError(JevClientError):
    def __init__(self, status_code: int) -> None:
        super().__init__("http", "Jev 服务返回了失败状态", status_code=status_code)


class ResponseDecodingError(JevClientError):
    def __init__(self) -> None:
        super().__init__("response_decoding", "Jev 服务返回了无效的 JSON")


class ResponseValidationError(JevClientError):
    """回答与它所声称对应的问题不匹配。

    ``reason`` 指明失败的校验项——是哪个问题、属于哪类不匹配——否则一个在
    此处中断的运行将无法诊断。它只描述结构，绝不包含提供方的载荷：按
    docs/security.md 的要求，响应体不会出现在错误文本中。
    """

    def __init__(self, reason: str | None = None) -> None:
        message = "Jev 服务的响应与预期的结构不匹配"
        if reason:
            message = f"{message}: {reason}"
        super().__init__("response_validation", message)
        self.reason = reason


@dataclass(frozen=True)
class JevClientConfig:
    api_key: str = field(repr=False)
    base_url: str = "https://api.typesafe.ai"
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("JEV_API_KEY 不得为空")
        if not self.base_url.startswith("https://"):
            raise ConfigurationError("JEV_BASE_URL 必须使用 HTTPS")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ConfigurationError("JEV_TIMEOUT_SECONDS 必须是有限的正数")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> JevClientConfig:
        env = os.environ if environ is None else environ
        key = env.get("JEV_API_KEY", "")
        if not key:
            raise ConfigurationError("必须提供 JEV_API_KEY")
        base_url = env.get("JEV_BASE_URL", "https://api.typesafe.ai")
        try:
            timeout = float(env.get("JEV_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise ConfigurationError("JEV_TIMEOUT_SECONDS 必须是数字") from exc
        return cls(api_key=key, base_url=base_url, timeout_seconds=timeout)


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: QuestionInstructions


class NoulQuestion(QuestionBase):
    type: str = "noul"
    criteria: Optional[QuestionInstructions] = None


class ChoiceQuestion(QuestionBase):
    type: str = "choice"
    criteria: dict[str, str]

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or len(value) > 255:
            raise ValueError("choice 的 criteria 必须包含 1 到 255 个候选项")
        return value


class ScoreQuestion(QuestionBase):
    type: str = "score"
    criteria: list[str]

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: list[str]) -> list[str]:
        if not 2 <= len(value) <= 10:
            raise ValueError("score 的 criteria 必须包含 2 到 10 个等级")
        return value


Question = Union[NoulQuestion, ChoiceQuestion, ScoreQuestion]


class AnswerBase(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str


class NoulAnswer(AnswerBase):
    type: str = "noul"
    noul: float

    @field_validator("noul")
    @classmethod
    def validate_noul(cls, value: float) -> float:
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("noul 概率必须是 0 到 1 之间的有限值")
        return value


class ChoiceAnswer(AnswerBase):
    type: str = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        _validate_distribution(value)
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        return _validate_probability(value, "confidence")


class ScoreAnswer(AnswerBase):
    type: str = "score"
    score: float
    legend: list[str]
    probabilities: dict[str, float]
    confidence: float

    @model_validator(mode="before")
    @classmethod
    def normalize_legend_shape(cls, data: Any) -> Any:
        """接收提供方以索引为键的 legend 与 probabilities。

        实际响应中 ``legend`` 形如 ``{"0": "No meaningful side
        effects", ...}``，``probabilities`` 也以同样的索引为键，而提交的
        criteria 是标签字符串。在此归一化可以让所有消费方看到同一种形状：
        legend 是标签的有序列表，probabilities 以标签为键。
        """
        if not isinstance(data, dict) or data.get("type") != "score":
            return data
        legend = data.get("legend")
        probabilities = data.get("probabilities")
        if not isinstance(legend, dict):
            return data
        ordered = sorted(legend.items(), key=lambda item: int(item[0]))
        normalized = {**data, "legend": [label for _, label in ordered]}
        if isinstance(probabilities, dict) and probabilities and all(
            key in legend for key in probabilities
        ):
            normalized["probabilities"] = {
                legend[key]: value for key, value in probabilities.items()
            }
        return normalized

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score 必须是有限值")
        return value

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        _validate_distribution(value)
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        return _validate_probability(value, "confidence")


Answer = Union[NoulAnswer, ChoiceAnswer, ScoreAnswer]


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")
    input_tokens: int
    output_tokens: int


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    answers: dict[str, Answer]
    usage: Usage


@dataclass
class JevClient:
    config: JevClientConfig
    transport: Optional[httpx.AsyncBaseTransport] = None

    async def systemone(
        self,
        *,
        model: str,
        state: Union[str, list[Any], dict[str, Any]],
        questions: Mapping[str, Question],
    ) -> DecisionResponse:
        if not model or not questions:
            raise RequestValidationError("必须提供 model 和至少一个问题")
        try:
            serialized_questions = {name: question.model_dump(exclude_none=True) for name, question in questions.items()}
            if any(not name.strip() for name in questions):
                raise ValueError("问题名称不得为空")
            payload = {"model": model, "state": state, "questions": serialized_questions}
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise RequestValidationError("请求中包含无法与 JSON 兼容的值") from exc

        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
            try:
                response = await client.post(
                    urljoin(self.config.base_url.rstrip("/") + "/", "v1/systemone"),
                    headers={"Authorization": "Bearer " + self.config.api_key},
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise TransportError("Jev 服务请求超时") from exc
            except httpx.RequestError as exc:
                raise TransportError("Jev 服务请求失败") from exc

        if response.is_error:
            raise HttpError(response.status_code)
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ResponseDecodingError() from exc
        try:
            result = DecisionResponse.model_validate(payload)
            _validate_answers(result, questions)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            raise ResponseValidationError(str(exc)) from exc
        return result


def _validate_probability(value: float, label: str) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label} 必须是 0 到 1 之间的有限值")
    return value


# 提供方会把每个概率四舍五入到两位小数，因此一个 N 项分布累加后合理地
# 可能落在 1 ± N * 0.005：路由层提交的八个动作就是 0.04。容差若比提供方
# 自身的精度更严格，就会把舍入噪声变成一次失败的运行——这是实际评测中
# 遇到过的问题。该上界仍然足够严格，能抓住真正损坏的分布（缺少候选项、
# 归一化错误）。
_DISTRIBUTION_TOLERANCE = 0.05


def _validate_distribution(values: Mapping[str, float]) -> None:
    if not values:
        raise ValueError("概率分布不得为空")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
        raise ValueError("概率必须是 0 到 1 之间的有限值")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=_DISTRIBUTION_TOLERANCE):
        raise ValueError("概率之和必须为 1")


def _validate_answers(response: DecisionResponse, questions: Mapping[str, Question]) -> None:
    if set(response.answers) != set(questions):
        raise ValueError("响应中的问题必须与请求中的问题一致")
    for name, question in questions.items():
        answer = response.answers[name]
        expected_type = question.type
        if answer.type != expected_type:
            raise ValueError("回答类型必须与问题类型一致")
        if isinstance(question, ChoiceQuestion):
            if not isinstance(answer, ChoiceAnswer):
                raise TypeError("choice 类型的问题需要 choice 类型的回答")
            if answer.choice not in question.criteria or set(answer.probabilities) != set(question.criteria):
                raise ValueError("choice 类型的回答必须与提交的 criteria 匹配")
        if isinstance(question, ScoreQuestion):
            if not isinstance(answer, ScoreAnswer):
                raise TypeError("score 类型的问题需要 score 类型的回答")
            if answer.legend != question.criteria or set(answer.probabilities) != set(question.criteria):
                raise ValueError("score 类型的回答必须与提交的 criteria 匹配")


def get_config_from_env(environ: Optional[Mapping[str, str]] = None) -> JevClientConfig:
    return JevClientConfig.from_env(environ)

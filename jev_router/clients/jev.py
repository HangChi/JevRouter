from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional, Union
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

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
        super().__init__("http", "Jev service returned an unsuccessful status", status_code=status_code)


class ResponseDecodingError(JevClientError):
    def __init__(self) -> None:
        super().__init__("response_decoding", "Jev service returned invalid JSON")


class ResponseValidationError(JevClientError):
    def __init__(self) -> None:
        super().__init__("response_validation", "Jev service response did not match the expected schema")


@dataclass(frozen=True)
class JevClientConfig:
    api_key: str = field(repr=False)
    base_url: str = "https://api.typesafe.ai"
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("JEV_API_KEY must not be empty")
        if not self.base_url.startswith("https://"):
            raise ConfigurationError("JEV_BASE_URL must use HTTPS")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ConfigurationError("JEV_TIMEOUT_SECONDS must be a finite positive number")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> JevClientConfig:
        env = os.environ if environ is None else environ
        key = env.get("JEV_API_KEY", "")
        if not key:
            raise ConfigurationError("JEV_API_KEY is required")
        base_url = env.get("JEV_BASE_URL", "https://api.typesafe.ai")
        try:
            timeout = float(env.get("JEV_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise ConfigurationError("JEV_TIMEOUT_SECONDS must be numeric") from exc
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
            raise ValueError("choice criteria must contain 1 to 255 candidates")
        return value


class ScoreQuestion(QuestionBase):
    type: str = "score"
    criteria: list[str]

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: list[str]) -> list[str]:
        if not 2 <= len(value) <= 10:
            raise ValueError("score criteria must contain 2 to 10 levels")
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
            raise ValueError("noul probability must be finite and between 0 and 1")
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

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
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
            raise RequestValidationError("model and at least one question are required")
        try:
            serialized_questions = {name: question.model_dump(exclude_none=True) for name, question in questions.items()}
            if any(not name.strip() for name in questions):
                raise ValueError("question names must not be empty")
            payload = {"model": model, "state": state, "questions": serialized_questions}
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise RequestValidationError("request contains invalid JSON-compatible values") from exc

        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
            try:
                response = await client.post(
                    urljoin(self.config.base_url.rstrip("/") + "/", "v1/systemone"),
                    headers={"Authorization": "Bearer " + self.config.api_key},
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise TransportError("Jev service request timed out") from exc
            except httpx.RequestError as exc:
                raise TransportError("Jev service request failed") from exc

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
            raise ResponseValidationError() from exc
        return result


def _validate_probability(value: float, label: str) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be finite and between 0 and 1")
    return value


def _validate_distribution(values: Mapping[str, float]) -> None:
    if not values:
        raise ValueError("probability distribution must not be empty")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
        raise ValueError("probabilities must be finite and between 0 and 1")
    if not math.isclose(sum(values.values()), 1.0, rel_tol=1e-3, abs_tol=1e-3):
        raise ValueError("probabilities must sum to 1")


def _validate_answers(response: DecisionResponse, questions: Mapping[str, Question]) -> None:
    if set(response.answers) != set(questions):
        raise ValueError("response questions must match request questions")
    for name, question in questions.items():
        answer = response.answers[name]
        expected_type = question.type
        if answer.type != expected_type:
            raise ValueError("answer type must match question type")
        if isinstance(question, ChoiceQuestion):
            if not isinstance(answer, ChoiceAnswer):
                raise TypeError("choice question requires choice answer")
            if answer.choice not in question.criteria or set(answer.probabilities) != set(question.criteria):
                raise ValueError("choice answer must match submitted criteria")
        if isinstance(question, ScoreQuestion):
            if not isinstance(answer, ScoreAnswer):
                raise TypeError("score question requires score answer")
            if answer.legend != question.criteria or set(answer.probabilities) != set(question.criteria):
                raise ValueError("score answer must match submitted criteria")


def get_config_from_env(environ: Optional[Mapping[str, str]] = None) -> JevClientConfig:
    return JevClientConfig.from_env(environ)

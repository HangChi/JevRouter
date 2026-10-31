from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jev_router.clients.jev import JevClientConfig
from jev_router.clients.llm import LLMClientConfig


class Settings(BaseModel):
    """API 层的启动配置。

    所有字段在启动时一次校验完，而不是用到才发现问题：配置错了就该在接第一个
    任务之前就失败。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    database_path: str = Field(min_length=1)
    workspace_root: str = Field(default="./workspace", min_length=1)
    max_steps: int = Field(default=8, ge=1)
    max_model_calls: int = Field(default=16, ge=1)
    completion_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    confirmation_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    risk_threshold: float = Field(default=2.5, ge=0.0, le=4.0)
    reasoning_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    route_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    api_token: str | None = Field(default=None, min_length=1)
    confirmation_ttl_seconds: int = Field(default=900, ge=1)
    jev: JevClientConfig
    llm_model: str | None = Field(default=None, min_length=1)
    llm: LLMClientConfig | None = None

    @field_validator("model", "database_path", "workspace_root")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空白")
        return value.strip()


    @field_validator("llm_model")
    @classmethod
    def _trimmed_llm_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("不能为空白")
        return value.strip()

    @model_validator(mode="after")
    def _llm_is_configured_as_a_pair(self) -> Settings:
        if (self.llm is None) != (self.llm_model is None):
            raise ValueError("llm 与 llm_model 必须成对配置")
        return self

    @field_validator("max_model_calls")
    @classmethod
    def _covers_route_and_verify(cls, value: int, info: Any) -> int:
        steps = info.data.get("max_steps")
        if steps is not None and value < 2 * steps:
            raise ValueError("max_model_calls 至少要允许每步一次路由和一次验证")
        return value

    def budget(self) -> Any:
        from jev_router.state import ExecutionBudget

        return ExecutionBudget(max_steps=self.max_steps, max_model_calls=self.max_model_calls)

    def policy_thresholds(self) -> Any:
        from jev_router.policy import PolicyThresholds

        return PolicyThresholds(
            confirmation=self.confirmation_threshold,
            risk=self.risk_threshold,
            reasoning=self.reasoning_threshold,
            confidence=self.route_confidence_threshold,
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env: Mapping[str, str] = os.environ if environ is None else environ
        model = env.get("JEV_MODEL", "")
        if not model.strip():
            raise ValueError("JEV_MODEL 是必填项")
        llm_key = env.get("LLM_API_KEY", "").strip()
        llm_model = env.get("LLM_MODEL", "").strip()
        if llm_key or llm_model:
            if not llm_key:
                raise ValueError("配置了 LLM_MODEL 却缺少 LLM_API_KEY")
            if not llm_model:
                raise ValueError("配置了 LLM_API_KEY 却缺少 LLM_MODEL")
            llm: LLMClientConfig | None = LLMClientConfig.from_env(environ)
        else:
            llm = None
            llm_model = ""
        token = env.get("JEV_API_TOKEN", "").strip()
        return cls(
            model=model,
            database_path=env.get("JEV_DATABASE_PATH", "traces.db"),
            workspace_root=env.get("JEV_WORKSPACE_ROOT", "./workspace"),
            max_steps=_positive_int(env, "JEV_MAX_STEPS", 8),
            max_model_calls=_positive_int(env, "JEV_MAX_MODEL_CALLS", 16),
            completion_threshold=_bounded(env, "JEV_COMPLETION_THRESHOLD", 0.75, 0.0, 1.0),
            confirmation_threshold=_bounded(env, "JEV_CONFIRMATION_THRESHOLD", 0.75, 0.0, 1.0),
            risk_threshold=_bounded(env, "JEV_RISK_THRESHOLD", 2.5, 0.0, 4.0),
            reasoning_threshold=_bounded(env, "JEV_REASONING_THRESHOLD", 0.70, 0.0, 1.0),
            route_confidence_threshold=_bounded(
                env, "JEV_ROUTE_CONFIDENCE_THRESHOLD", 0.75, 0.0, 1.0
            ),
            api_token=token or None,
            confirmation_ttl_seconds=_positive_int(env, "JEV_CONFIRMATION_TTL_SECONDS", 900),
            jev=JevClientConfig.from_env(environ),
            llm=llm,
            llm_model=llm_model if llm is not None else None,
        )


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < 1:
        raise ValueError(f"{name} 必须是正数")
    return value


def _bounded(
    env: Mapping[str, str], name: str, default: float, low: float, high: float
) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} 必须落在 {low} 与 {high} 之间")
    return value


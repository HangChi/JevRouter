from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jev_router.clients.jev import JevClientConfig


class Settings(BaseModel):
    """Startup configuration for the API layer.

    Everything is validated once at startup rather than discovered lazily, so a
    misconfigured deployment fails before it accepts a task.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    database_path: str = Field(min_length=1)
    workspace_root: str = Field(default="./workspace", min_length=1)
    max_steps: int = Field(default=8, ge=1)
    max_model_calls: int = Field(default=16, ge=1)
    completion_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    jev: JevClientConfig

    @field_validator("model", "database_path", "workspace_root")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("max_model_calls")
    @classmethod
    def _covers_route_and_verify(cls, value: int, info: Any) -> int:
        steps = info.data.get("max_steps")
        if steps is not None and value < 2 * steps:
            raise ValueError("max_model_calls must allow one route and one verify per step")
        return value

    def budget(self) -> Any:
        from jev_router.state import ExecutionBudget

        return ExecutionBudget(max_steps=self.max_steps, max_model_calls=self.max_model_calls)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env: Mapping[str, str] = os.environ if environ is None else environ
        model = env.get("JEV_MODEL", "")
        if not model.strip():
            raise ValueError("JEV_MODEL is required")
        return cls(
            model=model,
            database_path=env.get("JEV_DATABASE_PATH", "traces.db"),
            workspace_root=env.get("JEV_WORKSPACE_ROOT", "./workspace"),
            max_steps=_positive_int(env, "JEV_MAX_STEPS", 8),
            max_model_calls=_positive_int(env, "JEV_MAX_MODEL_CALLS", 16),
            completion_threshold=_probability(env, "JEV_COMPLETION_THRESHOLD", 0.75),
            jev=JevClientConfig.from_env(environ),
        )


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _probability(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value

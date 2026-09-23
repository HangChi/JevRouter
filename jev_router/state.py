from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


def _snapshot(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("state values must contain only finite numbers")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("state object keys must be strings")
        return MappingProxyType({key: _snapshot(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_snapshot(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_snapshot(item) for item in value)
    raise ValueError("state values must be JSON-compatible")


def _validate_counter(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class StepRecord:
    step: int
    action: str
    result: Any = None

    def __post_init__(self) -> None:
        _validate_counter(self.step, "step")
        if not self.action or self.action.strip() != self.action:
            raise ValueError("action must be non-empty and trimmed")
        object.__setattr__(self, "result", _snapshot(self.result))


@dataclass(frozen=True)
class TaskState:
    goal: str
    step: int = 0
    context: Any = None
    history: tuple[StepRecord, ...] = ()
    last_result: Any = None

    def __post_init__(self) -> None:
        if not self.goal or not self.goal.strip():
            raise ValueError("goal must not be empty")
        _validate_counter(self.step, "step")
        history = tuple(self.history)
        if len(history) != self.step:
            raise ValueError("history length must match completed step count")
        if any(record.step != index for index, record in enumerate(history, start=1)):
            raise ValueError("history steps must be consecutive and one-based")
        object.__setattr__(self, "context", _snapshot(self.context))
        object.__setattr__(self, "history", history)
        object.__setattr__(self, "last_result", _snapshot(self.last_result))

    def advance(self, action: str, result: Any = None) -> TaskState:
        next_step = self.step + 1
        record = StepRecord(step=next_step, action=action, result=result)
        return TaskState(
            goal=self.goal,
            step=next_step,
            context=self.context,
            history=(*self.history, record),
            last_result=record.result,
        )


@dataclass(frozen=True)
class ExecutionBudget:
    max_steps: int
    max_model_calls: int
    remaining_steps: int | None = None
    remaining_model_calls: int | None = None

    def __post_init__(self) -> None:
        _validate_counter(self.max_steps, "max_steps")
        _validate_counter(self.max_model_calls, "max_model_calls")
        steps = self.max_steps if self.remaining_steps is None else self.remaining_steps
        calls = self.max_model_calls if self.remaining_model_calls is None else self.remaining_model_calls
        _validate_counter(steps, "remaining_steps")
        _validate_counter(calls, "remaining_model_calls")
        if steps > self.max_steps or calls > self.max_model_calls:
            raise ValueError("remaining budget must not exceed its maximum")
        object.__setattr__(self, "remaining_steps", steps)
        object.__setattr__(self, "remaining_model_calls", calls)

    def consume_step(self) -> ExecutionBudget:
        if self.remaining_steps == 0:
            raise ValueError("step budget is exhausted")
        assert self.remaining_steps is not None
        return ExecutionBudget(
            max_steps=self.max_steps,
            max_model_calls=self.max_model_calls,
            remaining_steps=self.remaining_steps - 1,
            remaining_model_calls=self.remaining_model_calls,
        )

    def consume_model_call(self) -> ExecutionBudget:
        if self.remaining_model_calls == 0:
            raise ValueError("model-call budget is exhausted")
        assert self.remaining_model_calls is not None
        return ExecutionBudget(
            max_steps=self.max_steps,
            max_model_calls=self.max_model_calls,
            remaining_steps=self.remaining_steps,
            remaining_model_calls=self.remaining_model_calls - 1,
        )

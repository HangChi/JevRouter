from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from jev_router.state import ExecutionBudget, StepRecord, TaskState


def test_task_state_starts_with_empty_history() -> None:
    state = TaskState(goal="Find a record", context={"filters": ["active"]})

    assert state.step == 0
    assert state.history == ()
    assert state.context["filters"] == ("active",)


def test_advance_appends_a_step_and_preserves_previous_state() -> None:
    initial = TaskState(goal="Calculate", context={"inputs": [2, 2]})
    result = {"value": 4}

    advanced = initial.advance("calculator", result)
    result["value"] = 0

    assert initial.step == 0
    assert initial.history == ()
    assert advanced.step == 1
    assert advanced.history == (StepRecord(1, "calculator", {"value": 4}),)
    assert advanced.last_result["value"] == 4


def test_nested_input_is_snapshotted_on_construction() -> None:
    context: dict[str, Any] = {"nested": [1, {"ready": True}]}
    state = TaskState(goal="Inspect", context=context)
    context["nested"][1]["ready"] = False

    assert state.context["nested"][1]["ready"] is True
    with pytest.raises(TypeError):
        state.context["new"] = "value"


def test_goal_step_and_history_are_validated() -> None:
    with pytest.raises(ValueError, match="goal"):
        TaskState(goal="  ")
    with pytest.raises(ValueError, match="非负整数"):
        TaskState(goal="Inspect", step=-1)
    with pytest.raises(ValueError, match="history 长度"):
        TaskState(goal="Inspect", step=1)
    with pytest.raises(ValueError, match="连续"):
        TaskState(goal="Inspect", step=1, history=(StepRecord(2, "lookup"),))


def test_state_rejects_non_json_values_and_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="JSON 兼容"):
        TaskState(goal="Inspect", context={"unsupported": object()})
    with pytest.raises(ValueError, match="有限"):
        TaskState(goal="Inspect", context={"score": float("nan")})


def test_budget_starts_full_and_consumes_immutably() -> None:
    budget = ExecutionBudget(max_steps=2, max_model_calls=1)
    after_call = budget.consume_model_call()
    after_step = after_call.consume_step()

    assert (budget.remaining_steps, budget.remaining_model_calls) == (2, 1)
    assert (after_call.remaining_steps, after_call.remaining_model_calls) == (2, 0)
    assert (after_step.remaining_steps, after_step.remaining_model_calls) == (1, 0)


def test_zero_budgets_are_valid_and_exhausted() -> None:
    budget = ExecutionBudget(max_steps=0, max_model_calls=0)

    with pytest.raises(ValueError, match="步数预算已耗尽"):
        budget.consume_step()
    with pytest.raises(ValueError, match="模型调用预算已耗尽"):
        budget.consume_model_call()


def test_budget_rejects_invalid_limits_and_remaining_counts() -> None:
    with pytest.raises(ValueError, match="非负整数"):
        ExecutionBudget(max_steps=True, max_model_calls=1)
    with pytest.raises(ValueError, match="非负整数"):
        ExecutionBudget(max_steps=1, max_model_calls=1, remaining_steps=-1)
    with pytest.raises(ValueError, match="不得超过上限"):
        ExecutionBudget(max_steps=1, max_model_calls=1, remaining_model_calls=2)


def test_frozen_records_cannot_be_reassigned() -> None:
    state = TaskState(goal="Inspect")

    with pytest.raises(FrozenInstanceError):
        state.step = 1  # type: ignore[misc]

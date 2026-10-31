from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from jev_router.policy import PolicyEngine, PolicyThresholds
from jev_router.router import RouteDecision
from jev_router.tools.base import ToolResult
from jev_router.tools.registry import ToolRegistry


class StubInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1)


class StubTool:
    name = "lookup"
    description = "Read a local record"
    risk = "read"
    input_model = StubInput

    def __init__(self) -> None:
        self.executed = False

    def execute(self, input: dict[str, Any]) -> ToolResult:
        self.executed = True
        return ToolResult(tool_name=self.name, output=input)


def route(**changes: Any) -> RouteDecision:
    values: dict[str, Any] = {
        "action": "lookup",
        "confidence": 0.9,
        "risk": 1.0,
        "risk_confidence": 0.9,
        "requires_confirmation": 0.1,
        "needs_reasoning": 0.1,
        "model": "test-model",
    }
    values.update(changes)
    return RouteDecision(**values)


@pytest.fixture
def setup_policy() -> tuple[PolicyEngine, StubTool]:
    tool = StubTool()
    return PolicyEngine(ToolRegistry([tool])), tool


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("ask_user", "ask_user"),
        ("delegate_to_llm", "delegate_to_llm"),
        ("finish", "finish"),
    ],
)
def test_control_actions_map_directly(
    setup_policy: tuple[PolicyEngine, StubTool], action: str, expected: str
) -> None:
    policy, _ = setup_policy

    decision = policy.evaluate(route(action=action))

    assert decision.outcome == expected
    assert decision.action == action


def test_unknown_tool_is_rejected(setup_policy: tuple[PolicyEngine, StubTool]) -> None:
    policy, _ = setup_policy

    decision = policy.evaluate(route(action="not_registered"))

    assert decision.outcome == "reject"


@pytest.mark.parametrize(
    "changes",
    [
        {"requires_confirmation": 0.751},
        {"risk": 2.5},
    ],
)
def test_confirmation_thresholds_take_precedence(
    setup_policy: tuple[PolicyEngine, StubTool], changes: dict[str, float]
) -> None:
    policy, _ = setup_policy

    decision = policy.evaluate(route(needs_reasoning=0.9, confidence=0.5, **changes))

    assert decision.outcome == "ask_confirmation"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"requires_confirmation": 0.75, "risk": 2.49}, "execute"),
        ({"needs_reasoning": 0.70}, "execute"),
        ({"confidence": 0.75}, "execute"),
        ({"needs_reasoning": 0.701}, "delegate_to_llm"),
        ({"confidence": 0.749}, "delegate_to_llm"),
    ],
)
def test_policy_threshold_boundaries(
    setup_policy: tuple[PolicyEngine, StubTool],
    changes: dict[str, float],
    expected: str,
) -> None:
    policy, _ = setup_policy

    assert policy.evaluate(route(**changes)).outcome is expected


def test_action_is_rejected_with_empty_registry() -> None:
    policy = PolicyEngine(ToolRegistry())

    decision = policy.evaluate(route())

    assert decision.outcome == "reject"




def test_policy_never_executes_tools(setup_policy: tuple[PolicyEngine, StubTool]) -> None:
    policy, tool = setup_policy

    for decision_route in (
        route(),
        route(requires_confirmation=0.9),
        route(needs_reasoning=0.9),
        route(action="ask_user"),
        route(action="finish"),
        route(action="unknown"),
    ):
        policy.evaluate(decision_route)

    assert not tool.executed


class _RiskyTool(StubTool):
    """同一份实现，只改声明出来的副作用等级。"""

    def __init__(self, risk: str) -> None:
        super().__init__()
        self.risk = risk


@pytest.mark.parametrize("risk", ["write", "external"])
def test_declared_tool_risk_forces_confirmation(risk: str) -> None:
    """工具自报的等级优先于模型给出的低风险分。

    这是「确认 0/17」那类缺陷的结构性修复：只要工具声明了 write/external，
    即使路由认为它无害、置信度极高，也必须走确认。
    """
    tool = _RiskyTool(risk)
    policy = PolicyEngine(ToolRegistry([tool]))

    decision = policy.evaluate(
        route(requires_confirmation=0.0, risk=0.0, confidence=1.0, needs_reasoning=0.0)
    )

    assert decision.outcome == "ask_confirmation"
    assert risk in decision.reason


def test_read_tool_is_still_governed_by_probabilities() -> None:
    policy = PolicyEngine(ToolRegistry([_RiskyTool("read")]))

    assert policy.evaluate(route()).outcome == "execute"


def test_thresholds_are_configurable() -> None:
    policy = PolicyEngine(
        ToolRegistry([_RiskyTool("read")]),
        PolicyThresholds(confirmation=0.90, risk=3.5, reasoning=0.30, confidence=0.95),
    )

    # 收紧后的置信度阈值：0.94 不再足以自动执行。
    assert policy.evaluate(route(confidence=0.94)).outcome == "delegate_to_llm"
    # 收紧后的推理阈值：0.40 已经越过 0.30。
    assert policy.evaluate(route(needs_reasoning=0.4)).outcome == "delegate_to_llm"
    # 收紧后的确认阈值：0.85 仍低于 0.90，不触发；0.95 触发。
    assert (
        policy.evaluate(route(requires_confirmation=0.85, confidence=1.0)).outcome == "execute"
    )
    assert (
        policy.evaluate(route(requires_confirmation=0.95, confidence=1.0)).outcome
        == "ask_confirmation"
    )


def test_thresholds_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError):
        PolicyThresholds(confirmation=1.5)
    with pytest.raises(ValueError):
        PolicyThresholds(risk=9.0)


def test_policy_exposes_its_thresholds() -> None:
    thresholds = PolicyThresholds(confirmation=0.6)

    assert PolicyEngine(ToolRegistry(), thresholds).thresholds is thresholds
    assert PolicyThresholds().as_dict()["risk"] == 2.5

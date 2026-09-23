from __future__ import annotations

from typing import Any

import pytest

from jev_router.policy import PolicyEngine
from jev_router.router import RouteDecision
from jev_router.tools.base import ToolResult
from jev_router.tools.registry import ToolRegistry


class StubTool:
    name = "lookup"
    description = "Read a local record"
    risk = "read"

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

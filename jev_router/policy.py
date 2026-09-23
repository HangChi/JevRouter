from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from jev_router.router import RouteDecision
from jev_router.tools.registry import ToolRegistry

CONFIRMATION_THRESHOLD = 0.75
RISK_THRESHOLD = 2.5
REASONING_THRESHOLD = 0.70
ROUTE_CONFIDENCE_THRESHOLD = 0.75


PolicyOutcome = Literal[
    "execute",
    "ask_confirmation",
    "delegate_to_llm",
    "ask_user",
    "finish",
    "reject",
]


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    action: str
    reason: str


class PolicyEngine:
    def __init__(self, tools: ToolRegistry) -> None:
        self._tools = tools

    def evaluate(self, route: RouteDecision) -> PolicyDecision:
        controls = {
            "ask_user": ("ask_user", "The route requests more user information."),
            "delegate_to_llm": (
                "delegate_to_llm",
                "The route requests complex reasoning.",
            ),
            "finish": ("finish", "The route considers the task complete."),
        }
        if route.action in controls:
            outcome, reason = controls[route.action]
            return PolicyDecision(
                outcome=cast(PolicyOutcome, outcome), action=route.action, reason=reason
            )

        if route.action not in self._tools.names():
            return PolicyDecision(
                outcome="reject",
                action=route.action,
                reason="The recommended action is not registered.",
            )

        if (
            route.requires_confirmation > CONFIRMATION_THRESHOLD
            or route.risk >= RISK_THRESHOLD
        ):
            return PolicyDecision(
                outcome="ask_confirmation",
                action=route.action,
                reason="The route exceeds a confirmation threshold.",
            )

        if (
            route.needs_reasoning > REASONING_THRESHOLD
            or route.confidence < ROUTE_CONFIDENCE_THRESHOLD
        ):
            return PolicyDecision(
                outcome="delegate_to_llm",
                action=route.action,
                reason="The route exceeds a delegation threshold.",
            )

        return PolicyDecision(
            outcome="execute",
            action=route.action,
            reason="The registered action is permitted by the configured thresholds.",
        )

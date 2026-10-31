from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from jev_router.router import RouteDecision
from jev_router.tools.base import RiskLevel
from jev_router.tools.registry import ToolRegistry

# 工具声明的副作用等级里，哪些必须经过显式确认。
#
# 这条规则来自 docs/security.md：模型自报的风险分只是输入，不能作为授权依据。
# 写在策略引擎里而不是执行循环里，是为了让「线上真正怎么执行」和「评测怎么度量」
# 共用同一份判断——两处各写一遍就会漂移，而漂移的那一半一定是没人盯着的那一半。
CONFIRMING_RISKS: frozenset[RiskLevel] = frozenset({"write", "external"})

DEFAULT_CONFIRMATION_THRESHOLD = 0.75
DEFAULT_RISK_THRESHOLD = 2.5
DEFAULT_REASONING_THRESHOLD = 0.70
DEFAULT_CONFIDENCE_THRESHOLD = 0.75

# 旧的模块级常量保留给调用方与既有测试，语义等同于默认阈值。
CONFIRMATION_THRESHOLD = DEFAULT_CONFIRMATION_THRESHOLD
RISK_THRESHOLD = DEFAULT_RISK_THRESHOLD
REASONING_THRESHOLD = DEFAULT_REASONING_THRESHOLD
ROUTE_CONFIDENCE_THRESHOLD = DEFAULT_CONFIDENCE_THRESHOLD


PolicyOutcome = Literal[
    "execute",
    "ask_confirmation",
    "delegate_to_llm",
    "ask_user",
    "finish",
    "reject",
]


@dataclass(frozen=True)
class PolicyThresholds:
    """策略引擎的四个阈值。

    都是项目初值，不是服务商推荐值。改它应该由评测数据驱动，而不是手感——
    `evals --mode calibrate` 就是为此存在的。
    """

    confirmation: float = DEFAULT_CONFIRMATION_THRESHOLD
    risk: float = DEFAULT_RISK_THRESHOLD
    reasoning: float = DEFAULT_REASONING_THRESHOLD
    confidence: float = DEFAULT_CONFIDENCE_THRESHOLD

    def __post_init__(self) -> None:
        for name in ("confirmation", "reasoning", "confidence"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} 阈值必须落在 0 与 1 之间")
        if not 0.0 <= self.risk <= 4.0:
            raise ValueError("risk 阈值必须落在 0 与 4 之间")

    def as_dict(self) -> dict[str, float]:
        return {
            "confirmation": self.confirmation,
            "risk": self.risk,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    action: str
    reason: str


class PolicyEngine:
    """把一条路由建议映射成显式控制结果，自己不执行任何工具。

    判定顺序是有意的：控制动作 → 未注册拦截 → 工具风险下限 → 概率阈值。
    风险下限排在概率之前，意味着「工具本身危险」这个事实不会因为模型给出的
    低风险分而被绕过；反过来，模型认为风险高也依然可以触发确认。
    """

    def __init__(
        self,
        tools: ToolRegistry,
        thresholds: PolicyThresholds | None = None,
    ) -> None:
        self._tools = tools
        self._thresholds = thresholds or PolicyThresholds()

    @property
    def thresholds(self) -> PolicyThresholds:
        return self._thresholds

    def evaluate(self, route: RouteDecision) -> PolicyDecision:
        controls = {
            "ask_user": ("ask_user", "路由认为需要更多用户信息。"),
            "delegate_to_llm": ("delegate_to_llm", "路由认为需要更深的推理。"),
            "finish": ("finish", "路由认为任务已经完成。"),
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
                reason="该动作没有注册在任何工具上。",
            )

        # 注册表是一个活对象：`names()` 与 `get()` 之间它可能已经变了，
        # 也可能是个只实现了半只协议的实现。拿不到工具就当未注册处理，fail closed。
        try:
            tool = self._tools.get(route.action)
        except KeyError:
            return PolicyDecision(
                outcome="reject",
                action=route.action,
                reason="该动作没有注册在任何工具上。",
            )
        if tool.risk in CONFIRMING_RISKS:

            return PolicyDecision(
                outcome="ask_confirmation",
                action=route.action,
                reason=f"工具 {route.action} 声明为 {tool.risk} 风险，必须显式确认。",
            )

        if (
            route.requires_confirmation > self._thresholds.confirmation
            or route.risk >= self._thresholds.risk
        ):
            return PolicyDecision(
                outcome="ask_confirmation",
                action=route.action,
                reason="路由信号超过确认阈值。",
            )

        if (
            route.needs_reasoning > self._thresholds.reasoning
            or route.confidence < self._thresholds.confidence
        ):
            return PolicyDecision(
                outcome="delegate_to_llm",
                action=route.action,
                reason="路由信号超过委托阈值。",
            )

        return PolicyDecision(
            outcome="execute",
            action=route.action,
            reason="已注册动作落在当前阈值允许的范围内。",
        )

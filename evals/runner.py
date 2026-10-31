from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from evals.cases import EvalCase
from evals.llm_router import LLMRouter
from evals.metrics import ComparisonMetrics, summarize
from jev_router.clients.jev import JevClientError
from jev_router.policy import PolicyEngine, PolicyThresholds
from jev_router.router import Router
from jev_router.serialization import jsonable
from jev_router.tools.registry import ToolRegistry

EvalMode = Literal["jev", "llm", "compare"]

JEVMODE = "jev"
LLMMODE = "llm"

# 会中断自动执行、把控制权交给人工或 LLM 的结局。
# `finish` 是完成，`reject` 是失败，两者都不算升级。
_ESCALATING_OUTCOMES = frozenset({"ask_confirmation", "delegate_to_llm", "ask_user"})


@dataclass(frozen=True)
class CaseOutcome:
    """一个路由层在一个用例上的全部产出。

    ``mode`` 标出这条记录来自哪个路由层，因此 compare 运行会把同一个用例的
    两行都存下来，聚合时按 ``case_id`` 配对。

    末尾那五个信号字段是「原始证据」：置信度、风险分、确认概率、推理概率、
    工具风险等级。策略结果是由它们推出来的，把它们一起存下来，阈值校准才能
    离线重放而不必再花一次 provider 调用。
    """

    case_id: str
    goal: str
    expected_action: str
    allowed_actions: tuple[str, ...]
    requires_confirmation: bool
    mode: str
    action: str | None
    matched_expected: bool
    matched_allowed: bool
    succeeded: bool
    policy_outcome: str | None
    escalated: bool | None
    confirmation_requested: bool | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    confidence: float | None = None
    risk: float | None = None
    requires_confirmation_probability: float | None = None
    needs_reasoning_probability: float | None = None
    tool_risk: str | None = None



@dataclass(frozen=True)
class EvalReport:
    run_id: str
    mode: EvalMode
    created_at: str
    outcomes: tuple[CaseOutcome, ...]
    metrics: ComparisonMetrics


class EvalRunner:
    """把用例集重放进给定的路由层。

    路由层、策略引擎与工具注册表都是 agent 本身在用的那些对象，评测不引入
    任何新行为，只记录回来的东西。某个路由层抛异常时会产出一条错误记录而不是
    中断整轮，这样一个坏用例不会把另外四十九条一起藏起来。
    """

    def __init__(
        self,
        *,
        cases: Sequence[EvalCase],
        tools: ToolRegistry,
        jev_router: Router | None = None,
        llm_router: LLMRouter | None = None,
        thresholds: PolicyThresholds | None = None,
    ) -> None:
        if not cases:
            raise ValueError("at least one case is required")
        self._cases = tuple(cases)
        self._tools = tools
        self._jev = jev_router
        self._llm = llm_router
        self._policy = PolicyEngine(tools, thresholds)


    async def run(self, mode: EvalMode, *, run_id: str | None = None) -> EvalReport:
        if mode in (JEVMODE, "compare") and self._jev is None:
            raise ValueError(f"mode {mode!r} needs a Jev router")
        if mode in (LLMMODE, "compare") and self._llm is None:
            raise ValueError(f"mode {mode!r} needs an LLM baseline router")
        outcomes: list[CaseOutcome] = []
        for case in self._cases:
            if mode in (JEVMODE, "compare"):
                outcomes.append(await self._run_jev(case))
            if mode in (LLMMODE, "compare"):
                outcomes.append(await self._run_llm(case))
        return EvalReport(
            run_id=run_id or uuid4().hex,
            mode=mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            outcomes=tuple(outcomes),
            metrics=summarize(outcomes),
        )

    async def _run_jev(self, case: EvalCase) -> CaseOutcome:
        started = time.monotonic()
        try:
            route = await self._require_jev().route(_routing_state(case))
        except Exception as exc:  # noqa: BLE001 - 一个坏用例不能中断整轮
            return _error_outcome(case, JEVMODE, exc, _elapsed(started))
        latency_ms = _elapsed(started)
        policy = self._policy.evaluate(route)
        # 确认与否完全取自策略引擎的结论，与执行循环走的是同一条判断路径。
        confirmation_requested = policy.outcome == "ask_confirmation"
        return CaseOutcome(
            case_id=case.id,
            goal=case.goal,
            expected_action=case.expected_action,
            allowed_actions=case.allowed_actions,
            requires_confirmation=case.requires_confirmation,
            mode=JEVMODE,
            action=route.action,
            matched_expected=route.action == case.expected_action,
            matched_allowed=route.action in case.allowed_actions,
            succeeded=(
                route.action in case.allowed_actions
                and confirmation_requested == case.requires_confirmation
            ),
            policy_outcome=policy.outcome,
            escalated=policy.outcome in _ESCALATING_OUTCOMES,
            confirmation_requested=confirmation_requested,
            latency_ms=latency_ms,
            input_tokens=route.input_tokens,
            output_tokens=route.output_tokens,
            error=None,
            confidence=route.confidence,
            risk=route.risk,
            requires_confirmation_probability=route.requires_confirmation,
            needs_reasoning_probability=route.needs_reasoning,
            tool_risk=_tool_risk(self._tools, route.action),
        )

    async def _run_llm(self, case: EvalCase) -> CaseOutcome:
        started = time.monotonic()
        try:
            decision = await self._require_llm().route(_routing_state(case))
        except Exception as exc:  # noqa: BLE001 - 一个坏用例不能中断整轮
            return _error_outcome(case, LLMMODE, exc, _elapsed(started))
        return CaseOutcome(
            case_id=case.id,
            goal=case.goal,
            expected_action=case.expected_action,
            allowed_actions=case.allowed_actions,
            requires_confirmation=case.requires_confirmation,
            mode=LLMMODE,
            action=decision.action,
            matched_expected=decision.action == case.expected_action,
            matched_allowed=decision.action in case.allowed_actions,
            succeeded=decision.action in case.allowed_actions,
            policy_outcome=None,
            escalated=None,
            confirmation_requested=None,
            latency_ms=decision.latency_ms,
            input_tokens=decision.input_tokens,
            output_tokens=decision.output_tokens,
            error=None,
            tool_risk=_tool_risk(self._tools, decision.action),
        )


    def _require_jev(self) -> Router:
        assert self._jev is not None
        return self._jev

    def _require_llm(self) -> LLMRouter:
        assert self._llm is not None
        return self._llm


def _routing_state(case: EvalCase) -> dict[str, Any]:
    """与执行循环发出的路由载荷一致，对应用例的第一步。"""
    return {
        "goal": case.goal,
        "step": 0,
        "context": jsonable(case.context) if case.context is not None else {},
        "history": [],
        "last_result": None,
    }


def _tool_risk(tools: ToolRegistry, action: str | None) -> str | None:
    """动作背后的工具风险等级；控制动作与非注册动作没有工具，返回 ``None``。"""
    if action is None:
        return None
    try:
        return tools.get(action).risk
    except KeyError:
        return None



def _error_outcome(
    case: EvalCase, mode: str, exc: BaseException, latency_ms: int
) -> CaseOutcome:
    detail = str(exc) or exc.__class__.__name__
    if isinstance(exc, JevClientError):
        detail = f"{exc.category}: {detail}"
    return CaseOutcome(
        case_id=case.id,
        goal=case.goal,
        expected_action=case.expected_action,
        allowed_actions=case.allowed_actions,
        requires_confirmation=case.requires_confirmation,
        mode=mode,
        action=None,
        matched_expected=False,
        matched_allowed=False,
        succeeded=False,
        policy_outcome=None,
        escalated=None,
        confirmation_requested=None,
        latency_ms=latency_ms,
        input_tokens=None,
        output_tokens=None,
        error=detail,
    )


def _elapsed(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))

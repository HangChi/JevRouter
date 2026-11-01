from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol
from uuid import uuid4

from jev_router.clients.jev import JevClient, JevClientError
from jev_router.policy import PolicyDecision, PolicyEngine, PolicyOutcome, PolicyThresholds
from jev_router.router import RouteDecision, Router
from jev_router.serialization import jsonable
from jev_router.state import ExecutionBudget, TaskState
from jev_router.tools.base import Tool
from jev_router.tools.registry import ToolRegistry
from jev_router.verifier import VerificationDecision, Verifier

RunStatus = Literal[
    "completed",
    "needs_user_input",
    "needs_confirmation",
    "rejected",
    "budget_exhausted",
    "failed",
]

DEFAULT_COMPLETION_THRESHOLD = 0.75


class ActionInputResolver(Protocol):
    async def resolve(self, action: str, state: TaskState) -> Mapping[str, Any]: ...


class ConfirmationHandler(Protocol):
    async def confirm(
        self,
        task_id: str,
        action: str,
        arguments: Mapping[str, Any],
        state: TaskState,
    ) -> bool: ...


class UserInputHandler(Protocol):
    async def request_input(self, question: str, state: TaskState) -> str | None: ...


class DelegateHandler(Protocol):
    async def delegate(self, state: TaskState) -> str: ...


class TraceSink(Protocol):
    def emit(self, trace: StepTrace) -> None: ...


@dataclass(frozen=True)
class StepTrace:
    step: int
    task_id: str
    action: str
    executed: bool = False
    result: Any = None
    policy_outcome: PolicyOutcome | None = None
    policy_reason: str | None = None
    route_confidence: float | None = None
    route_risk: float | None = None
    requires_confirmation: float | None = None
    needs_reasoning: float | None = None
    confirmed: bool | None = None
    arguments: Mapping[str, Any] | None = None
    verification: VerificationDecision | None = None
    state_snapshot: Mapping[str, Any] | None = None
    model: str | None = None
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if self.arguments is not None:
            object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        if self.state_snapshot is not None:
            object.__setattr__(self, "state_snapshot", MappingProxyType(dict(self.state_snapshot)))


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    task_id: str
    state: TaskState
    budget: ExecutionBudget
    traces: tuple[StepTrace, ...]
    diagnostic: str | None = None


class _Stop(Exception):
    """跳出循环迭代的非局部出口，携带一个终态。"""

    def __init__(self, status: RunStatus, diagnostic: str | None = None) -> None:
        self.status = status
        self.diagnostic = diagnostic
        super().__init__(diagnostic or status)


@dataclass(frozen=True)
class _Verified:
    budget: ExecutionBudget
    assessment: VerificationDecision | None = None
    status: RunStatus | None = None
    diagnostic: str | None = None


@dataclass
class _Draft:
    step: int
    task_id: str
    state_snapshot: Mapping[str, Any]
    action: str = ""
    executed: bool = False
    result: Any = None
    confirmed: bool | None = None
    arguments: Mapping[str, Any] | None = None
    route: RouteDecision | None = None
    policy: PolicyDecision | None = None
    verification: VerificationDecision | None = None


class Runner:
    """有界的 route / policy / execute / verify 循环。

    预算在何时消耗、循环在何时停止，都由这里决定。路由层、策略引擎与验证器
    都从同一个 ToolRegistry 装配，因此「执行前再查一次注册表」这道检查无法被
    另一个注册表实例绕开。
    """

    def __init__(
        self,
        *,
        client: JevClient,
        model: str,
        tools: ToolRegistry,
        budget: ExecutionBudget,
        completion_threshold: float = DEFAULT_COMPLETION_THRESHOLD,
        thresholds: PolicyThresholds | None = None,
        resolver: ActionInputResolver | None = None,
        confirmation: ConfirmationHandler | None = None,
        user_input: UserInputHandler | None = None,
        delegate: DelegateHandler | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        if not model or not model.strip():
            raise ValueError("model 不能为空")
        if not math.isfinite(completion_threshold) or not 0 <= completion_threshold <= 1:
            raise ValueError("completion_threshold 必须是 0 到 1 之间的有限数")
        if budget.max_model_calls < 2 * budget.max_steps:
            raise ValueError("max_model_calls 至少要允许每步一次路由和一次验证")
        self._client = client
        self._model = model
        self._tools = tools
        self._budget = budget
        self._completion_threshold = completion_threshold
        self._resolver = resolver
        self._confirmation = confirmation
        self._user_input = user_input
        self._delegate = delegate
        self._trace_sink = trace_sink
        self._router = Router(client, model, tools)
        self._policy = PolicyEngine(tools, thresholds)
        self._verifier = Verifier(client, model)


    async def run(
        self,
        goal: str,
        *,
        task_id: str | None = None,
        context: Any = None,
    ) -> RunResult:
        identifier = task_id or uuid4().hex
        state = TaskState(goal=goal, context=context)
        budget = self._budget
        traces: list[StepTrace] = []
        verified: TaskState | None = None

        while True:
            step = state.step + 1
            started = time.monotonic()
            snapshot = self._routing_state(state)
            draft = _Draft(step=step, task_id=identifier, state_snapshot=snapshot)
            try:
                if budget.remaining_steps == 0 or budget.remaining_model_calls == 0:
                    raise _Stop("budget_exhausted", "步数或模型调用预算已耗尽")
                budget = budget.consume_step()
                budget = budget.consume_model_call()

                try:
                    route = await self._router.route(snapshot)
                except JevClientError as exc:
                    raise _Stop("failed", f"路由请求失败：{exc.category}") from exc
                draft.route = route
                policy = self._policy.evaluate(route)
                draft.policy = policy
                draft.action = policy.action

                if policy.outcome == "reject":
                    raise _Stop("rejected", policy.reason)

                if policy.outcome == "ask_user":
                    answer = await self._request_input(policy.action, state)
                    if answer is None:
                        raise _Stop(
                            "needs_user_input",
                            "路由请求了更多用户信息，但没有拿到回答",
                        )
                    state = self._advance(state, "ask_user", {"user_input": answer})
                    draft.result = {"user_input": answer}
                    self._collect(draft, started, traces)
                    continue

                if policy.outcome == "delegate_to_llm":
                    if self._delegate is None:
                        raise _Stop(
                            "failed", "路由要求委托，但没有配置委托处理器"
                        )
                    if budget.remaining_model_calls == 0:
                        raise _Stop(
                            "budget_exhausted",
                            "模型调用预算在委托之前就已耗尽",
                        )
                    budget = budget.consume_model_call()
                    answer = await self._delegate.delegate(state)
                    if answer is None:
                        raise _Stop("failed", "委托处理器没有返回结果")
                    state = self._advance(state, "delegate_to_llm", answer)
                    draft.result = answer
                    self._collect(draft, started, traces)
                    continue

                if policy.outcome in ("execute", "ask_confirmation"):
                    state, budget = await self._execute(
                        draft, state, budget, policy, identifier
                    )
                elif state.step == 0:
                    # 路由建议 finish，但还没有任何可验证的步骤。
                    raise _Stop(
                        "completed",
                        "路由在任何步骤执行之前就认为任务已完成",
                    )

                checked = await self._verify(state, budget, verified)
                budget = checked.budget
                draft.verification = checked.assessment
                if checked.status is not None:
                    raise _Stop(checked.status, checked.diagnostic or "验证未通过")
                assert checked.assessment is not None
                if checked.assessment.completion_probability >= self._completion_threshold:
                    raise _Stop("completed")
                verified = state
                self._collect(draft, started, traces)
            except _Stop as stop:
                return self._settle(
                    draft, stop.status, state, budget, traces, stop.diagnostic, started
                )

    async def _execute(
        self,
        draft: _Draft,
        state: TaskState,
        budget: ExecutionBudget,
        policy: PolicyDecision,
        task_id: str,
    ) -> tuple[TaskState, ExecutionBudget]:
        tool = self._lookup(policy.action)
        if tool is None:
            raise _Stop("rejected", f"动作 {policy.action!r} 已不在注册表中")
        arguments = await self._resolve_arguments(policy.action, state)
        if arguments is None:
            raise _Stop(
                "failed",
                f"the resolver did not return an argument mapping for {policy.action!r}",
            )
        draft.arguments = arguments
        if self._needs_confirmation(policy):
            approved = (
                False
                if self._confirmation is None
                else await self._confirmation.confirm(task_id, policy.action, arguments, state)
            )
            draft.confirmed = approved
            if not approved:
                raise _Stop("needs_confirmation", "没有得到显式确认")
        try:
            result = tool.execute(dict(arguments))
        except ValueError as exc:
            raise _Stop(
                "failed", f"tool {policy.action!r} rejected its input: {exc}"
            ) from exc
        draft.result = result.output
        draft.executed = True
        state = self._advance(state, policy.action, result.output)
        return state, budget

    async def _verify(
        self,
        state: TaskState,
        budget: ExecutionBudget,
        verified: TaskState | None,
    ) -> _Verified:
        if budget.remaining_model_calls == 0:
            return _Verified(
                budget=budget,
                status="budget_exhausted",
                diagnostic="模型调用预算在验证之前就已耗尽",
            )
        budget = budget.consume_model_call()
        try:
            assessment = await self._verifier.verify(state)
        except JevClientError as exc:
            return _Verified(
                budget=budget,
                status="failed",
                diagnostic=f"验证请求失败：{exc.category}",
            )
        except ValueError as exc:
            return _Verified(
                budget=budget,
                status="failed",
                diagnostic=f"验证被拒绝：{exc}",
            )
        if assessment.completion_probability < self._completion_threshold and verified is state:
            # 这条守卫实际只能由 finish 触发：其余分支（执行工具、委托、追问）
            # 都会推进状态，两次验证之间状态对象必然不同。所以它测的是
            # 「路由说做完了，验证器不同意」——这是两个判断者的分歧，不是卡死。
            # 工作可能真的做完了（工具结果就在 trace 里），该交给人判断，
            # 而不是由代码替人下「失败」的结论。
            return _Verified(
                budget=budget,
                assessment=assessment,
                status="needs_confirmation",
                diagnostic=(
                    "路由认为任务已经完成，但验证器对同一状态连续给出低于阈值的"
                    f"完成概率（{assessment.completion_probability:.2f} < "
                    f"{self._completion_threshold:.2f}）；"
                    "工具结果可能已经达成目标，是否接受这个结果需要人工判断"
                ),
            )
        return _Verified(budget=budget, assessment=assessment)

    async def _request_input(self, question: str, state: TaskState) -> str | None:
        if self._user_input is None:
            return None
        return await self._user_input.request_input(question, state)

    async def _resolve_arguments(
        self, action: str, state: TaskState
    ) -> Mapping[str, Any] | None:
        if self._resolver is None:
            return {}
        resolved = await self._resolver.resolve(action, state)
        if not isinstance(resolved, Mapping):
            return None
        return resolved

    def _advance(self, state: TaskState, action: str, result: Any) -> TaskState:
        try:
            return state.advance(action, result)
        except ValueError as exc:
            raise _Stop(
                "failed", f"state could not record the result of {action!r}: {exc}"
            ) from exc

    def _lookup(self, action: str) -> Tool | None:
        try:
            return self._tools.get(action)
        except KeyError:
            return None

    @staticmethod
    def _needs_confirmation(policy: PolicyDecision) -> bool:
        """是否需要人工确认，只由策略引擎的结论决定。

        这里刻意不再重复「工具风险等级」的判断：同一套规则写在两个地方，
        迟早会在其中一处被人改掉，而另一处继续按老规则放行。
        """
        return policy.outcome == "ask_confirmation"

    @staticmethod
    def _routing_state(state: TaskState) -> dict[str, Any]:
        return {
            "goal": state.goal,
            "step": state.step,
            "context": jsonable(state.context),
            "history": [
                {"step": record.step, "action": record.action, "result": jsonable(record.result)}
                for record in state.history
            ],
            "last_result": jsonable(state.last_result),
        }

    def _settle(
        self,
        draft: _Draft,
        status: RunStatus,
        state: TaskState,
        budget: ExecutionBudget,
        traces: list[StepTrace],
        diagnostic: str | None,
        started: float,
    ) -> RunResult:
        self._collect(draft, started, traces)
        return RunResult(
            status=status,
            task_id=draft.task_id,
            state=state,
            budget=budget,
            traces=tuple(traces),
            diagnostic=diagnostic,
        )

    def _collect(self, draft: _Draft, started: float, traces: list[StepTrace]) -> None:
        trace = self._seal(draft, started)
        traces.append(trace)
        if self._trace_sink is None:
            return
        try:
            self._trace_sink.emit(trace)
        except Exception:  # noqa: BLE001, S110
            # A live sink is caller code and may raise anything; the trace is
            # already recorded in RunResult.traces, so only real-time delivery is
            # lost and the run must not abort because of it.
            pass

    def _seal(self, draft: _Draft, started: float) -> StepTrace:
        route = draft.route
        policy = draft.policy
        return StepTrace(
            step=draft.step,
            task_id=draft.task_id,
            action=draft.action,
            executed=draft.executed,
            result=draft.result,
            policy_outcome=None if policy is None else policy.outcome,
            policy_reason=None if policy is None else policy.reason,
            route_confidence=None if route is None else route.confidence,
            route_risk=None if route is None else route.risk,
            requires_confirmation=None if route is None else route.requires_confirmation,
            needs_reasoning=None if route is None else route.needs_reasoning,
            confirmed=draft.confirmed,
            arguments=draft.arguments,
            verification=draft.verification,
            state_snapshot=draft.state_snapshot,
            model=None if route is None else route.model,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

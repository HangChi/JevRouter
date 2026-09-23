from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol
from uuid import uuid4

from jev_router.clients.jev import JevClient, JevClientError
from jev_router.policy import PolicyDecision, PolicyEngine, PolicyOutcome
from jev_router.router import RouteDecision, Router
from jev_router.serialization import jsonable
from jev_router.state import ExecutionBudget, TaskState
from jev_router.tools.base import RiskLevel, Tool
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

# docs/security.md maps these tool risk levels to mandatory confirmation. The
# Policy Engine phase deliberately left the coarse category unenforced, so the
# Runner has to apply it before any side effect happens.
_CONFIRMING_RISKS: frozenset[RiskLevel] = frozenset({"write", "external"})


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
    """Non-local exit from a loop iteration, carrying a terminal run status."""

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
    """Bounded route/policy/execute/verify loop over the injected Jev client.

    The Runner owns when budgets are consumed and when the loop stops. Router,
    PolicyEngine and Verifier are assembled here from a single shared
    ToolRegistry so the execution-time registration recheck cannot be bypassed by
    a divergent registry instance.
    """

    def __init__(
        self,
        *,
        client: JevClient,
        model: str,
        tools: ToolRegistry,
        budget: ExecutionBudget,
        completion_threshold: float = DEFAULT_COMPLETION_THRESHOLD,
        resolver: ActionInputResolver | None = None,
        confirmation: ConfirmationHandler | None = None,
        user_input: UserInputHandler | None = None,
        delegate: DelegateHandler | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        if not model or not model.strip():
            raise ValueError("model must not be empty")
        if not math.isfinite(completion_threshold) or not 0 <= completion_threshold <= 1:
            raise ValueError("completion_threshold must be finite and between 0 and 1")
        if budget.max_model_calls < 2 * budget.max_steps:
            raise ValueError("max_model_calls must allow one route and one verify per step")
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
        self._policy = PolicyEngine(tools)
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
                    raise _Stop("budget_exhausted", "step or model-call budget is exhausted")
                budget = budget.consume_step()
                budget = budget.consume_model_call()

                try:
                    route = await self._router.route(snapshot)
                except JevClientError as exc:
                    raise _Stop("failed", f"route request failed: {exc.category}") from exc
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
                            "more user information was requested but not provided",
                        )
                    state = self._advance(state, "ask_user", {"user_input": answer})
                    draft.result = {"user_input": answer}
                    self._collect(draft, started, traces)
                    continue

                if policy.outcome == "delegate_to_llm":
                    if self._delegate is None:
                        raise _Stop(
                            "failed", "delegation was requested but no handler is configured"
                        )
                    if budget.remaining_model_calls == 0:
                        raise _Stop(
                            "budget_exhausted",
                            "model-call budget is exhausted before delegation",
                        )
                    budget = budget.consume_model_call()
                    answer = await self._delegate.delegate(state)
                    if answer is None:
                        raise _Stop("failed", "the delegate handler returned no result")
                    state = self._advance(state, "delegate_to_llm", answer)
                    draft.result = answer
                    self._collect(draft, started, traces)
                    continue

                if policy.outcome in ("execute", "ask_confirmation"):
                    state, budget = await self._execute(
                        draft, state, budget, policy, identifier
                    )
                elif state.step == 0:
                    # A finish recommendation with nothing to verify yet.
                    raise _Stop(
                        "completed",
                        "the router considered the task complete before any step ran",
                    )

                checked = await self._verify(state, budget, verified)
                budget = checked.budget
                draft.verification = checked.assessment
                if checked.status is not None:
                    raise _Stop(checked.status, checked.diagnostic or "verification did not pass")
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
            raise _Stop("rejected", f"action {policy.action!r} is no longer registered")
        arguments = await self._resolve_arguments(policy.action, state)
        if arguments is None:
            raise _Stop(
                "failed",
                f"the resolver did not return an argument mapping for {policy.action!r}",
            )
        draft.arguments = arguments
        if self._needs_confirmation(policy, tool):
            approved = (
                False
                if self._confirmation is None
                else await self._confirmation.confirm(task_id, policy.action, arguments, state)
            )
            draft.confirmed = approved
            if not approved:
                raise _Stop("needs_confirmation", "explicit confirmation was not granted")
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
                diagnostic="model-call budget is exhausted before verification",
            )
        budget = budget.consume_model_call()
        try:
            assessment = await self._verifier.verify(state)
        except JevClientError as exc:
            return _Verified(
                budget=budget,
                status="failed",
                diagnostic=f"verification request failed: {exc.category}",
            )
        except ValueError as exc:
            return _Verified(
                budget=budget,
                status="failed",
                diagnostic=f"verification was rejected: {exc}",
            )
        if assessment.completion_probability < self._completion_threshold and verified is state:
            return _Verified(
                budget=budget,
                assessment=assessment,
                status="failed",
                diagnostic="the verifier reported no progress on an unchanged state",
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
    def _needs_confirmation(policy: PolicyDecision, tool: Tool) -> bool:
        if policy.outcome == "ask_confirmation":
            return True
        return tool.risk in _CONFIRMING_RISKS

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

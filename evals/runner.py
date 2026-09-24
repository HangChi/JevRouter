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
from jev_router.policy import PolicyEngine
from jev_router.router import Router
from jev_router.serialization import jsonable
from jev_router.tools.registry import ToolRegistry

EvalMode = Literal["jev", "llm", "compare"]

JEVMODE = "jev"
LLMMODE = "llm"

# Outcomes that stop automatic execution and hand control to a human or the LLM.
# `finish` is completion, and `reject` is a failure, so neither is an escalation.
_ESCALATING_OUTCOMES = frozenset({"ask_confirmation", "delegate_to_llm", "ask_user"})


@dataclass(frozen=True)
class CaseOutcome:
    """What one router did with one case.

    ``mode`` is the router that produced the row, so a compare run stores both
    rows for a case and the aggregation pairs them by ``case_id``.
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


@dataclass(frozen=True)
class EvalReport:
    run_id: str
    mode: EvalMode
    created_at: str
    outcomes: tuple[CaseOutcome, ...]
    metrics: ComparisonMetrics


class EvalRunner:
    """Replays the case set through the routers it is given.

    The routers, the policy engine and the tool registry are the same objects
    the agent uses; the eval adds no behaviour, it only records what came back.
    A router that raises produces an error outcome instead of aborting the run,
    so one bad case cannot hide the other forty-nine.
    """

    def __init__(
        self,
        *,
        cases: Sequence[EvalCase],
        tools: ToolRegistry,
        jev_router: Router | None = None,
        llm_router: LLMRouter | None = None,
    ) -> None:
        if not cases:
            raise ValueError("at least one case is required")
        self._cases = tuple(cases)
        self._jev = jev_router
        self._llm = llm_router
        self._policy = PolicyEngine(tools)

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
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            return _error_outcome(case, JEVMODE, exc, _elapsed(started))
        latency_ms = _elapsed(started)
        policy = self._policy.evaluate(route)
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
        )

    async def _run_llm(self, case: EvalCase) -> CaseOutcome:
        started = time.monotonic()
        try:
            decision = await self._require_llm().route(_routing_state(case))
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
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
        )

    def _require_jev(self) -> Router:
        assert self._jev is not None
        return self._jev

    def _require_llm(self) -> LLMRouter:
        assert self._llm is not None
        return self._llm


def _routing_state(case: EvalCase) -> dict[str, Any]:
    """The same routing payload the Runner sends, for a case's first step."""
    return {
        "goal": case.goal,
        "step": 0,
        "context": jsonable(case.context) if case.context is not None else {},
        "history": [],
        "last_result": None,
    }


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

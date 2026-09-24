"""Shared offline doubles for the Jev provider.

Every test drives the core through ``httpx.MockTransport``, so no test reaches
the network, needs a credential, or produces a billable request.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from apps.api.schemas import (
    ComparisonMetricsPayload,
    EvalCaseOutcomePayload,
    LatencyPayload,
    ModeMetricsPayload,
    RecordEvalRunRequest,
)
from jev_router.router import RISK_LEVELS
from jev_router.state import TaskState
from jev_router.verifier import QUALITY_LEVELS

CALCULATOR_CANDIDATES = ("calculator", "ask_user", "delegate_to_llm", "finish")
WRITE_FILE_CANDIDATES = ("write_file", "ask_user", "delegate_to_llm", "finish")
EMAIL_CANDIDATES = ("send_mock_email", "ask_user", "delegate_to_llm", "finish")
OPAQUE_CANDIDATES = ("opaque", "ask_user", "delegate_to_llm", "finish")

TEST_MODEL = "test-model"


class FakeJev:
    """Serves canned systemone responses, keyed by which question set was asked."""

    def __init__(self, *, fail_verify_transport: bool = False) -> None:
        self.routes: list[dict[str, Any]] = []
        self.verifies: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.fail_verify_transport = fail_verify_transport

    def transport(self) -> httpx.MockTransport:
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.requests.append(payload)
            if self.fail_verify_transport and "task_complete" in payload["questions"]:
                raise httpx.ConnectError("verification endpoint is unreachable")
            queue = self.routes if "next_action" in payload["questions"] else self.verifies
            if not queue:
                raise AssertionError("the runner issued more Jev requests than expected")
            return httpx.Response(
                200,
                json={
                    "model": TEST_MODEL,
                    "answers": queue.pop(0),
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )

        return httpx.MockTransport(handler)

    def route_calls(self) -> int:
        return sum(1 for item in self.requests if "next_action" in item["questions"])

    def verify_calls(self) -> int:
        return sum(1 for item in self.requests if "task_complete" in item["questions"])


class StubResolver:
    """Stands in for the LLM-backed argument synthesis a later phase will supply."""

    def __init__(self, arguments: Any = None) -> None:
        self.arguments = arguments if arguments is not None else {"expression": "2 + 2"}
        self.calls: list[tuple[str, TaskState]] = []

    async def resolve(self, action: str, state: TaskState) -> Any:
        self.calls.append((action, state))
        return self.arguments


def choice_answer(
    action: str,
    candidates: tuple[str, ...],
    confidence: float = 0.9,
) -> dict[str, Any]:
    probabilities = {name: 0.0 for name in candidates}
    probabilities[action] = 1.0
    return {
        "type": "choice",
        "choice": action,
        "probabilities": probabilities,
        "confidence": confidence,
    }


def risk_answer(score: float = 1.0, confidence: float = 0.8) -> dict[str, Any]:
    return {
        "type": "score",
        "score": score,
        "legend": list(RISK_LEVELS),
        "probabilities": {level: 0.2 for level in RISK_LEVELS},
        "confidence": confidence,
    }


def route_answers(
    action: str = "calculator",
    candidates: tuple[str, ...] = CALCULATOR_CANDIDATES,
    *,
    confidence: float = 0.9,
    risk: float = 1.0,
    requires_confirmation: float = 0.1,
    needs_reasoning: float = 0.1,
) -> dict[str, Any]:
    return {
        "next_action": choice_answer(action, candidates, confidence),
        "risk": risk_answer(risk),
        "requires_confirmation": {"type": "noul", "noul": requires_confirmation},
        "needs_reasoning": {"type": "noul", "noul": needs_reasoning},
    }


def verify_answers(completion: float = 0.82, quality: float = 3.0) -> dict[str, Any]:
    return {
        "task_complete": {"type": "noul", "noul": completion},
        "result_quality": {
            "type": "score",
            "score": quality,
            "legend": list(QUALITY_LEVELS),
            "probabilities": {level: 0.25 for level in QUALITY_LEVELS},
            "confidence": 0.6,
        },
    }


def case_outcome(
    case_id: str,
    *,
    mode: str = "jev",
    action: str | None = "calculator",
    matched_expected: bool = True,
    latency_ms: int = 120,
) -> EvalCaseOutcomePayload:
    return EvalCaseOutcomePayload(
        case_id=case_id,
        goal="what is 2 + 2?",
        expected_action="calculator",
        allowed_actions=["calculator"],
        requires_confirmation=False,
        mode=mode,
        action=action,
        matched_expected=matched_expected,
        matched_allowed=action is not None,
        succeeded=action is not None and matched_expected,
        policy_outcome="execute" if mode == "jev" else None,
        escalated=False if mode == "jev" else None,
        confirmation_requested=False if mode == "jev" else None,
        latency_ms=latency_ms,
        input_tokens=10,
        output_tokens=5,
        error=None,
    )


def eval_run(
    run_id: str = "run-1",
    *,
    mode: str = "compare",
    case_ids: tuple[str, ...] = ("case-1", "case-2"),
    created_at: str = "2026-09-24T00:00:00+00:00",
) -> RecordEvalRunRequest:
    outcomes: list[EvalCaseOutcomePayload] = []
    for case_id in case_ids:
        if mode in ("jev", "compare"):
            outcomes.append(case_outcome(case_id, mode="jev"))
        if mode in ("llm", "compare"):
            outcomes.append(
                case_outcome(case_id, mode="llm", action="web_search", matched_expected=False)
            )
    metrics = ComparisonMetricsPayload(
        jev=ModeMetricsPayload(
            mode="jev",
            case_count=len(case_ids),
            error_count=0,
            expected_match_count=len(case_ids),
            allowed_match_count=len(case_ids),
            success_count=len(case_ids),
            escalation_count=0,
            confirmation_expected_count=0,
            confirmation_requested_count=0,
            confirmation_match_count=0,
            expected_match_rate=1.0,
            allowed_match_rate=1.0,
            success_rate=1.0,
            error_rate=0.0,
            escalation_rate=0.0,
            latency=LatencyPayload(mean_ms=100.0, p50_ms=100, p95_ms=100, max_ms=100),
            input_tokens={"mean": 10.0, "total": 20},
            output_tokens={"mean": 5.0, "total": 10},
        ),
        llm=ModeMetricsPayload(
            mode="llm",
            case_count=len(case_ids),
            error_count=0,
            expected_match_count=0,
            allowed_match_count=0,
            success_count=0,
            expected_match_rate=0.0,
            allowed_match_rate=0.0,
            success_rate=0.0,
            error_rate=0.0,
            latency=LatencyPayload(mean_ms=900.0, p50_ms=900, p95_ms=900, max_ms=900),
            input_tokens={"mean": 300.0, "total": 600},
            output_tokens={"mean": 12.0, "total": 24},
        ),
        agreement_count=0,
        compared_count=len(case_ids),
        agreement_rate=0.0,
        disagreement_case_ids=list(case_ids),
    )
    return RecordEvalRunRequest(
        run_id=run_id,
        mode=mode,
        created_at=created_at,
        outcomes=outcomes,
        metrics=metrics,
    )

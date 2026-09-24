from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# API-level statuses for a run that has not reached a terminal RunStatus yet.
RUNNING = "running"
AWAITING_CONFIRMATION = "awaiting_confirmation"
AWAITING_INPUT = "awaiting_input"


class SubmitTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] | None = None

    @field_validator("goal")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal must not be blank")
        return value


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: str


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class ProvideInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)


class PendingConfirmationView(BaseModel):
    action: str
    arguments: dict[str, Any]
    step: int


class PendingInputView(BaseModel):
    question: str
    step: int


class TaskView(BaseModel):
    task_id: str
    goal: str
    status: str
    step: int
    diagnostic: str | None = None
    pending_confirmation: PendingConfirmationView | None = None
    pending_input: PendingInputView | None = None


class TaskSummary(BaseModel):
    task_id: str
    goal: str
    status: str
    step: int


class TaskListResponse(BaseModel):
    tasks: list[TaskSummary]


class TraceView(BaseModel):
    step: int
    action: str
    policy_outcome: str | None = None
    policy_reason: str | None = None
    executed: bool = False
    result: Any | None = None
    route_confidence: float | None = None
    route_risk: float | None = None
    requires_confirmation: float | None = None
    needs_reasoning: float | None = None
    confirmed: bool | None = None
    arguments: dict[str, Any] | None = None
    completion_probability: float | None = None
    quality_score: float | None = None
    state_snapshot: dict[str, Any] | None = None
    duration_ms: int = 0

    @classmethod
    def from_trace(cls, trace: Any) -> TraceView:
        verification = trace.verification
        return cls(
            step=trace.step,
            action=trace.action,
            policy_outcome=trace.policy_outcome,
            policy_reason=trace.policy_reason,
            executed=trace.executed,
            result=trace.result,
            route_confidence=trace.route_confidence,
            route_risk=trace.route_risk,
            requires_confirmation=trace.requires_confirmation,
            needs_reasoning=trace.needs_reasoning,
            confirmed=trace.confirmed,
            arguments=None if trace.arguments is None else dict(trace.arguments),
            completion_probability=(
                None if verification is None else verification.completion_probability
            ),
            quality_score=None if verification is None else verification.quality_score,
            state_snapshot=None if trace.state_snapshot is None else dict(trace.state_snapshot),
            duration_ms=trace.duration_ms,
        )


class TraceListResponse(BaseModel):
    task_id: str
    traces: list[TraceView]


class EvalCaseOutcomePayload(BaseModel):
    """One stored case outcome, exactly as the eval runner reported it.

    ``extra="forbid"`` and the range constraints keep a hand-edited or drifted
    report from being stored as if it were a real run.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    expected_action: str = Field(min_length=1)
    allowed_actions: list[str] = Field(min_length=1)
    requires_confirmation: bool
    mode: str = Field(min_length=1)
    action: str | None = None
    matched_expected: bool
    matched_allowed: bool
    succeeded: bool
    policy_outcome: str | None = None
    escalated: bool | None = None
    confirmation_requested: bool | None = None
    latency_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    error: str | None = None


class LatencyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_ms: float = Field(ge=0)
    p50_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    max_ms: int = Field(ge=0)


class TokenStatsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean: float = Field(ge=0)
    total: int = Field(ge=0)


class ModeMetricsPayload(BaseModel):
    """One router's aggregate over a run.

    The policy fields stay ``None`` for the LLM baseline: it produces no
    probabilities, so it has no policy outcome to escalate or confirm, and
    storing zero there would claim a fact the baseline cannot have.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1)
    case_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    expected_match_count: int = Field(ge=0)
    allowed_match_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    escalation_count: int | None = Field(default=None, ge=0)
    confirmation_expected_count: int | None = Field(default=None, ge=0)
    confirmation_requested_count: int | None = Field(default=None, ge=0)
    confirmation_match_count: int | None = Field(default=None, ge=0)
    expected_match_rate: float = Field(ge=0, le=1)
    allowed_match_rate: float = Field(ge=0, le=1)
    success_rate: float = Field(ge=0, le=1)
    error_rate: float = Field(ge=0, le=1)
    escalation_rate: float | None = Field(default=None, ge=0, le=1)
    latency: LatencyPayload
    input_tokens: TokenStatsPayload | None = None
    output_tokens: TokenStatsPayload | None = None


class ComparisonMetricsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jev: ModeMetricsPayload | None = None
    llm: ModeMetricsPayload | None = None
    agreement_count: int | None = Field(default=None, ge=0)
    compared_count: int | None = Field(default=None, ge=0)
    agreement_rate: float | None = Field(default=None, ge=0, le=1)
    disagreement_case_ids: list[str] = Field(default_factory=list)


EVAL_MODES = ("jev", "llm", "compare")
_MODE_ROUTERS: dict[str, frozenset[str]] = {
    "jev": frozenset({"jev"}),
    "llm": frozenset({"llm"}),
    "compare": frozenset({"jev", "llm"}),
}


class RecordEvalRunRequest(BaseModel):
    """A finished eval run, posted by the eval CLI.

    ``case_count`` is not part of the body: it is derived from the distinct case
    ids, so a report cannot claim a case count its own rows contradict.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    outcomes: list[EvalCaseOutcomePayload] = Field(min_length=1)
    metrics: ComparisonMetricsPayload

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in EVAL_MODES:
            raise ValueError(f"mode must be one of {', '.join(EVAL_MODES)}")
        return value

    @model_validator(mode="after")
    def _outcomes_match_the_mode(self) -> RecordEvalRunRequest:
        allowed = _MODE_ROUTERS[self.mode]
        if any(outcome.mode not in allowed for outcome in self.outcomes):
            raise ValueError(f"mode {self.mode!r} cannot carry outcomes from another router")
        if self.mode == "compare":
            by_mode: dict[str, set[str]] = {}
            for outcome in self.outcomes:
                by_mode.setdefault(outcome.mode, set()).add(outcome.case_id)
            if set(by_mode) != {"jev", "llm"} or by_mode["jev"] != by_mode["llm"]:
                raise ValueError("a compare run must pair every case across both routers")
        return self


class RecordEvalRunResponse(BaseModel):
    run_id: str
    case_count: int


class EvalRunSummary(BaseModel):
    run_id: str
    mode: str
    created_at: str
    case_count: int


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunSummary]


class EvalRunView(BaseModel):
    run_id: str
    mode: str
    created_at: str
    case_count: int
    metrics: ComparisonMetricsPayload
    outcomes: list[EvalCaseOutcomePayload]

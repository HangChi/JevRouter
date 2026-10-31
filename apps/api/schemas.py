from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# 一次运行还没到终态的 API 层状态。
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
            raise ValueError("goal 不能为空白")
        return value


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: str


class ConfirmRequest(BaseModel):
    """回应一次待确认。

    ``digest`` 不是可选的：它把这次批准钉死在「哪个任务、哪个动作、哪份参数」上，
    否则一次批准可以被复用到后来换过的参数上。取值来自 ``GET /tasks/{id}``
    返回的 ``pending_confirmation.digest``。
    """

    model_config = ConfigDict(extra="forbid")

    approved: bool
    digest: str = Field(min_length=1, max_length=64)


class ProvideInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)


class PendingConfirmationView(BaseModel):
    action: str
    arguments: dict[str, Any]
    step: int
    digest: str
    expires_at: str


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
    """一条已落库的用例结果，与评测运行器报出来的形状完全一致。

    ``extra="forbid"`` 加上取值范围约束，让手工改过或已经漂移的报告无法被当作
    一次真实运行存下来。

    末尾五个信号字段是可选的：它们从第十二阶段之后的运行才开始记录，早期报告
    没有这些字段，但仍应能被读取。
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
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk: float | None = Field(default=None, ge=0)
    requires_confirmation_probability: float | None = Field(default=None, ge=0, le=1)
    needs_reasoning_probability: float | None = Field(default=None, ge=0, le=1)
    tool_risk: str | None = None



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
    """一个路由层在一轮评测上的聚合结果。

    LLM 基线的策略字段保持 ``None``：它不产生概率，也就没有可升级或可确认的
    策略结论，存成 0 等于替它宣称一个它不可能有的事实。
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


class PolicyThresholdView(BaseModel):
    """当前生效的四个策略阈值，外加完成度阈值。

    把这些值暴露出来，是为了让「这一次为什么被拦下」可以被解释：仪表盘与
    校准结果都要拿它做对照，而不是各自硬编码一份副本。
    """

    confirmation: float
    risk: float
    reasoning: float
    confidence: float
    completion: float


class ToolPolicyView(BaseModel):
    """一个工具在策略层的样子：它声明了什么风险，因此需不需要确认。"""

    name: str
    risk: str
    description: str
    requires_confirmation: bool


class PolicyView(BaseModel):
    thresholds: PolicyThresholdView
    tools: list[ToolPolicyView]
    confirmation_ttl_seconds: int
    confirmation_binding: str

